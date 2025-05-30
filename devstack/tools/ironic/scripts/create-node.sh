#!/usr/bin/env bash

# **create-nodes**

# Creates baremetal poseur nodes for ironic testing purposes

set -ex

# Make tracing more educational
export PS4='+ ${BASH_SOURCE:-}:${FUNCNAME[0]:-}:L${LINENO:-}:   '

# Keep track of the DevStack directory
TOP_DIR=$(cd $(dirname "$0")/.. && pwd)

while getopts "n:c:i:m:M:d:a:b:e:E:p:o:f:l:L:N:A:D:v:P:t:B:s:" arg; do
    case $arg in
        n) NAME=$OPTARG;;
        c) CPU=$OPTARG;;
        i) INTERFACE_COUNT=$OPTARG;;
        M) INTERFACE_MTU=$OPTARG;;
        m) MEM=$(( 1024 * OPTARG ));;
        # Extra G to allow fuzz for partition table : flavor size and registered
        # size need to be different to actual size.
        d) DISK=$(( OPTARG + 1 ));;
        a) ARCH=$OPTARG;;
        b) BRIDGE=$OPTARG;;
        e) EMULATOR=$OPTARG;;
        E) ENGINE=$OPTARG;;
        p) VBMC_PORT=$OPTARG;;
        o) PDU_OUTLET=$OPTARG;;
        f) DISK_FORMAT=$OPTARG;;
        l) LOGDIR=$OPTARG;;
        L) UEFI_LOADER=$OPTARG;;
        N) UEFI_NVRAM=$OPTARG;;
        A) MAC_ADDRESS=$OPTARG;;
        D) NIC_DRIVER=$OPTARG;;
        v) VOLUME_COUNT=$OPTARG;;
        P) STORAGE_POOL=$OPTARG;;
        t) MACHINE_TYPE=$OPTARG;;
        B) BLOCK_SIZE=$OPTARG;;
        s) NET_SIMULATOR=$OPTARG;;
    esac
done

shift $(( $OPTIND - 1 ))

if [ -z "$UEFI_LOADER" ] && [ ! -z "$UEFI_NVRAM" ]; then
    echo "Parameter -N (UEFI NVRAM) cannot be used without -L (UEFI Loader)"
    exit 1
fi

LIBVIRT_NIC_DRIVER=${NIC_DRIVER:-"e1000"}
LIBVIRT_STORAGE_POOL=${STORAGE_POOL:-"default"}
LIBVIRT_CONNECT_URI=${LIBVIRT_CONNECT_URI:-"qemu:///system"}

export VIRSH_DEFAULT_CONNECT_URI=$LIBVIRT_CONNECT_URI

if [ -n "$LOGDIR" ] ; then
    mkdir -p "$LOGDIR"
fi

PREALLOC=
if [ -f /etc/debian_version -a "$DISK_FORMAT" == "qcow2" ]; then
    PREALLOC="--prealloc-metadata"
fi

if [ -n "$LOGDIR" ] ; then
    VM_LOGGING="--console-log $LOGDIR/${NAME}_console.log"
else
    VM_LOGGING=""
fi

UEFI_OPTS=""
if [ ! -z "$UEFI_LOADER" ]; then
    UEFI_OPTS="--uefi-loader $UEFI_LOADER"

    if [ ! -z "$UEFI_NVRAM" ]; then
        UEFI_OPTS+=" --uefi-nvram $UEFI_NVRAM"
    fi
fi

BLOCK_SIZE=${BLOCK_SIZE:-512}

# Create bridge and add VM interface to it.
# Additional interface will be added to this bridge and
# it will be plugged to OVS.
# This is needed in order to have interface in OVS even
# when VM is in shutdown state
INTERFACE_COUNT=${INTERFACE_COUNT:-1}

if [[ "${NET_SIMULATOR:-ovs}" == "ovs" ]]; then
    for int in $(seq 1 $INTERFACE_COUNT); do
        ovsif=ovs-${NAME}i${int}
        sudo ovs-vsctl --no-wait add-port $BRIDGE $ovsif
    done
else
    for int in $(seq 1 $INTERFACE_COUNT); do
        # NOTE(TheJulia): A simulator's setup will need to come along
        # and identify all of the simulators for required configuration.
        # NOTE(TheJulia): It would be way easier if we just sequentally
        # numbered *all* interfaces together, but the per-vm execution
        # model of this script makes it... difficult.
        simif=sim-${NAME}i${int}
        tapif=tap-${NAME}i${int}
        # NOTE(vsaienko) use veth pair here to ensure that interface
        # exists when VMs are turned off.
        sudo ip link add dev $tapif type veth peer name $simif || true
        for l in $tapif $simif; do
            sudo ip link set dev $l up
            sudo ip link set $l mtu $INTERFACE_MTU
        done
    done
fi

if [ -n "$MAC_ADDRESS" ] ; then
    MAC_ADDRESS="--mac $MAC_ADDRESS"
fi

VOLUME_COUNT=${VOLUME_COUNT:-1}

if ! virsh list --all | grep -q $NAME; then
    vm_opts=""
    for int in $(seq 1 $VOLUME_COUNT); do
        if [[ "$int" == "1" ]]; then
            # Compatibility with old naming
            vol_name="$NAME.$DISK_FORMAT"
        else
            vol_name="$NAME-$int.$DISK_FORMAT"
        fi
        virsh vol-list --pool $LIBVIRT_STORAGE_POOL | grep -q $vol_name &&
            virsh vol-delete $vol_name --pool $LIBVIRT_STORAGE_POOL >&2
        virsh vol-create-as $LIBVIRT_STORAGE_POOL ${vol_name} ${DISK}G --allocation 0 --format $DISK_FORMAT $PREALLOC >&2
        volume_path=$(virsh vol-path --pool $LIBVIRT_STORAGE_POOL $vol_name)
        # Pre-touch the VM to set +C, as it can only be set on empty files.
        sudo touch "$volume_path"
        sudo chattr +C "$volume_path" || true
        vm_opts+="--image $volume_path "
    done
    if [[ -n "$EMULATOR" ]]; then
        vm_opts+="--emulator $EMULATOR "
    fi

    $PYTHON $TOP_DIR/scripts/configure-vm.py \
        --bootdev network --name $NAME \
        --arch $ARCH --cpus $CPU --memory $MEM --libvirt-nic-driver $LIBVIRT_NIC_DRIVER \
        --disk-format $DISK_FORMAT $VM_LOGGING --engine $ENGINE $UEFI_OPTS $vm_opts \
        --interface-count $INTERFACE_COUNT $MAC_ADDRESS --machine_type $MACHINE_TYPE \
        --block-size $BLOCK_SIZE --mtu ${INTERFACE_MTU} --net_simulator ${NET_SIMULATOR:-ovs} >&2
fi

# echo mac in format mac1,ovs-node-0i1;mac2,ovs-node-0i2;...;macN,ovs-node0iN
# NOTE(TheJulia): Based upon the interface format, we need to search for slightly
# different output from the script run because we have to use different attachment
# names.
if [[ "${NET_SIMULATOR:-ovs}" == "ovs" ]]; then
    VM_MAC=$(echo -n $(virsh domiflist $NAME |awk '/ovs-/{print $5","$1}')|tr ' ' ';')
else
    VM_MAC=$(echo -n $(virsh domiflist $NAME |awk '/tap-/{print $5","$1}')|tr ' ' ';')
fi
echo -n "$VM_MAC $VBMC_PORT $PDU_OUTLET"
