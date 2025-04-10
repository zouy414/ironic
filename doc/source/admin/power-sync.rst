=====================
Power Synchronization
=====================

Baremetal Power Sync
====================
Each Baremetal conductor process runs a periodic task which synchronizes the
power state of the nodes between its database and the actual hardware. If the
value of the :oslo.config:option:`conductor.force_power_state_during_sync`
option is set to ``true`` the power state in the database will be forced on
the hardware and if it is set to ``false`` the hardware state will be forced
on the database. If this periodic task is enabled, it runs at an interval
defined by the :oslo.config:option:`conductor.sync_power_state_interval`
config option for those nodes which are not in maintenance. The requests sent
to Baseboard Management Controllers (BMCs) are done with a parallelism
controlled by :oslo.config:option:`conductor.sync_power_state_workers`.
The motivation to send out requests to BMCs in parallel is to handle
misbehaving BMCs which may delay or even block the synchronization otherwise.

.. note::
    In deployments with many nodes and IPMI as the configured BMC protocol,
    the default values of a 60 seconds power sync interval and 8 worker
    threads may lead to a high rate of required retries due to client-side UDP
    packet loss (visible via the corresponding warnings in the conductor
    logs). While Ironic automatically retries to get the power status
    for the affected nodes, the failure rate may be reduced by increasing
    the power sync cycle, e.g. to 300 seconds, and/or by reducing the number
    of power sync workers, e.g. to 2. Please keep in mind, however, that
    depending on the concrete setup increasing the power sync interval may
    have an impact on other components relying on up-to-date power states.

Compute-Baremetal Power Sync
============================
Each ``nova-compute`` process in the Compute service runs a periodic task which
synchronizes the power state of servers between its database and the compute
driver. If enabled, it runs at an interval defined by the
``sync_power_state_interval`` config option on the ``nova-compute`` process.
In case of the compute driver being baremetal driver, this sync will happen
between the databases of the compute and baremetal services. Since the sync
happens on the ``nova-compute`` process, the state in the compute database
will be forced on the baremetal database in case of inconsistencies. Hence a
node which was put down using the compute service API cannot be brought up
through the baremetal service API since the power sync task will regard the
compute service's knowledge of the power state as the source of truth. In order
to get around this disadvantage of the compute-baremetal power sync,
baremetal service does power state change callbacks to the compute service
using external events.

Power State Change Callbacks to the Compute Service
---------------------------------------------------

Whenever the Baremetal service changes the power state of a node, it can issue
a notification to the Compute service. The Compute service will consume this
notification and update the power state of the instance in its database.
By conveying all the power state changes to the compute service, the baremetal
service becomes the source of truth thus preventing the compute service from
forcing wrong power states on the physical instance during the
compute-baremetal power sync. It also adds the possibility of bringing
up/down a physical instance through the baremetal service API even if it was
put down/up through the compute service API.

This change requires the :oslo.config:group:`nova` section and the necessary
authentication options like the :oslo.config:option:`nova.auth_url` to be
defined in the configuration file of the baremetal service. If it is not
configured the baremetal service will not be able to send notifications to the
compute service and it will fall back to the behaviour of the compute service
forcing power states on the baremetal service during the power sync.
See :oslo.config:group:`nova` group for more details on the available config
options.

In case of baremetal stand alone deployments where there is no compute service
running, the :oslo.config:option:`nova.send_power_notifications` config option
should be set to ``False`` to disable power state change callbacks to the
compute service.

.. note::
    The baremetal service sends notifications to the compute service only if
    the target power state is ``power on`` or ``power off``. Other error
    and ``None`` states will be ignored. In situations where the power state
    change is originally coming from the compute service, the notification
    will still be sent by the baremetal service and it will be a no-op on the
    compute service side with a debug log stating the node is already powering
    on/off.

.. note::
    Although an exclusive lock is used when sending notifications to the
    compute service, there can still be a race condition if the
    compute-baremetal power sync happens to happen a nano-second before the
    power state change event is received from the baremetal service in which
    case the power state from compute service's database will be forced on the
    node.

.. _power-fault:

Power fault and recovery
========================

When `Baremetal Power Sync`_ is enabled, and the Bare Metal service loses
access to a node (usually because of invalid credentials, BMC issues or
networking interruptions), the node enters ``maintenance`` mode and its
``fault`` field is set to ``power failure``. The exact reason is stored in the
``maintenance_reason`` field.

As always with maintenance mode, only a subset of operations will work on such
nodes, and both the Compute service and the Ironic's native allocation API will
refuse to pick them. Any in-progress operations will either pause or fail.

The conductor responsible for the node will try to recover the connection
periodically (with the interval configured by the
:oslo.config:option:`conductor.power_failure_recovery_interval` option). If the
power sync is successful, the ``fault`` field is unset and the node leaves the
maintenance mode.

.. note::
   This only applies to automatic maintenance mode with the ``fault`` field
   set. Maintenance mode set manually is never left automatically.

Alternatively, you can disable maintenance mode yourself once the problem is
resolved::

       baremetal node maintenance unset <IRONIC NODE>
