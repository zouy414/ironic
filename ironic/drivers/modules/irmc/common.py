# Copyright 2015 FUJITSU LIMITED
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""
Common functionalities shared between different iRMC modules.
"""
import json
import os
import re

from oslo_log import log as logging
from oslo_serialization import jsonutils
from oslo_utils import importutils
from oslo_utils import strutils

from ironic.common import exception
from ironic.common.i18n import _
from ironic.common import utils
from ironic.conf import CONF
from ironic.drivers.modules import snmp
from ironic.drivers import utils

scci = importutils.try_import('scciclient.irmc.scci')
elcm = importutils.try_import('scciclient.irmc.elcm')

LOG = logging.getLogger(__name__)


IRMC_OS_NAME_R = re.compile(r'iRMC\s+S\d+')
IRMC_OS_NAME_NUM_R = re.compile(r'\d+$')
IRMC_FW_VER_R = re.compile(r'\d(\.\d+)*\w*')
IRMC_FW_VER_NUM_R = re.compile(r'\d(\.\d+)*')

IPMI_ENABLED_BY_DEFAULT_RANGES = {
    # iRMC S4 enables IPMI over LAN by default
    '4': None,
    # iRMC S5 enables IPMI over LAN by default
    '5': None,
    # iRMC S6 disables IPMI over LAN by default from version 2.00
    '6': {'upper': '2.00'}}

ELCM_STATUS_PATH = '/rest/v1/Oem/eLCM/eLCMStatus'

# List of xxx_interface & implementation pair which uses SNMP internally
# and iRMC driver supports
INTERFACE_IMPL_LIST_WITH_SNMP = {
    'inspect_interface': {'irmc', },
    'power_interface': {'irmc', }}

REQUIRED_PROPERTIES = {
    'irmc_address': _("IP address or hostname of the iRMC. Required."),
    'irmc_username': _("Username for the iRMC with administrator privileges. "
                       "Required."),
    'irmc_password': _("Password for irmc_username. Required."),
}
OPTIONAL_PROPERTIES = {
    'irmc_port': _("Port to be used for iRMC operations; either 80 or 443. "
                   "The default value is 443. Optional."),
    'irmc_auth_method': _("Authentication method for iRMC operations; "
                          "either 'basic' or 'digest'. The default value is "
                          "'basic'. Optional."),
    'irmc_client_timeout': _("Timeout (in seconds) for iRMC operations. "
                             "The default value is 60. Optional."),
    'irmc_sensor_method': _("Sensor data retrieval method; either "
                            "'ipmitool' or 'scci'. The default value is "
                            "'ipmitool'. Optional."),
}
OPTIONAL_DRIVER_INFO_PROPERTIES = {
    'irmc_verify_ca': _('Either a Boolean value, a path to a CA_BUNDLE '
                        'file or directory with certificates of trusted '
                        'CAs. If set to True the driver will verify the '
                        'host certificates; if False the driver will '
                        'ignore verifying the SSL certificate. If it\'s '
                        'a path the driver will use the specified '
                        'certificate or one of the certificates in the '
                        'directory. Defaults to True. Optional'),
}

SNMP_PROPERTIES = {
    'irmc_snmp_version': _("SNMP protocol version; either 'v1', 'v2c', or "
                           "'v3'. The default value is 'v2c'. Optional."),
    'irmc_snmp_port': _("SNMP port. The default is 161. Optional."),
    'irmc_snmp_community': _("SNMP community required for versions 'v1' and "
                             "'v2c'. The default value is 'public'. "
                             "Optional."),
}

SNMP_V3_REQUIRED_PROPERTIES = {
    'irmc_snmp_user': _("SNMPv3 User-based Security Model (USM) username. "
                        "Required for version 'v3’. "),
    'irmc_snmp_auth_password': _("SNMPv3 message authentication key. Must be "
                                 "8+ characters long. Required when message "
                                 "authentication is used."),
    'irmc_snmp_priv_password': _("SNMPv3 message privacy key. Must be 8+ "
                                 "characters long. Required when message "
                                 "privacy is used."),
}

SNMP_V3_OPTIONAL_PROPERTIES = {
    'irmc_snmp_auth_proto': _("SNMPv3 message authentication protocol ID. "
                              "Required for version 'v3'. "
                              "If using iRMC S4/S5, only 'sha' is supported."
                              "If using iRMC S6, the valid options are "
                              "'sha256', 'sha384', 'sha512'."),
    'irmc_snmp_priv_proto': _("SNMPv3 message privacy (encryption) protocol "
                              "ID. Required for version 'v3'. "
                              "'aes' is supported."),
}

SNMP_V3_DEPRECATED_PROPERTIES = {
    'irmc_snmp_security': _("SNMP security name required for version 'v3'. "
                            "Optional. Deprecated."),
}


COMMON_PROPERTIES = REQUIRED_PROPERTIES.copy()
COMMON_PROPERTIES.update(OPTIONAL_PROPERTIES)
COMMON_PROPERTIES.update(OPTIONAL_DRIVER_INFO_PROPERTIES)
COMMON_PROPERTIES.update(SNMP_PROPERTIES)
COMMON_PROPERTIES.update(SNMP_V3_REQUIRED_PROPERTIES)
COMMON_PROPERTIES.update(SNMP_V3_OPTIONAL_PROPERTIES)
COMMON_PROPERTIES.update(SNMP_V3_DEPRECATED_PROPERTIES)


def parse_driver_info(node):
    """Gets the specific Node driver info.

    This method validates whether the 'driver_info' property of the
    supplied node contains the required information for this driver.

    :param node: An ironic node object.
    :returns: A dict containing information from driver_info
        and default values.
    :raises: InvalidParameterValue if invalid value is contained
        in the 'driver_info' property.
    :raises: MissingParameterValue if some mandatory key is missing
        in the 'driver_info' property.
    """
    info = node.driver_info
    missing_info = [key for key in REQUIRED_PROPERTIES if not info.get(key)]
    if missing_info:
        raise exception.MissingParameterValue(_(
            "Missing the following iRMC parameters in node's"
            " driver_info: %s.") % missing_info)

    req = {key: value for key, value in info.items()
           if key in REQUIRED_PROPERTIES}
    # corresponding config names don't have 'irmc_' prefix
    opt = {param: info.get(param, CONF.irmc.get(param[len('irmc_'):]))
           for param in OPTIONAL_PROPERTIES}
    opt_driver_info = {param: info.get(param)
                       for param in OPTIONAL_DRIVER_INFO_PROPERTIES}
    d_info = dict(req, **opt, **opt_driver_info)
    d_info['irmc_port'] = utils.validate_network_port(
        d_info['irmc_port'], 'irmc_port')

    error_msgs = []
    if (d_info['irmc_auth_method'].lower() not in ('basic', 'digest')):
        error_msgs.append(
            _("Value '%s' is not supported for 'irmc_auth_method'.") %
            d_info['irmc_auth_method'])
    if d_info['irmc_port'] not in (80, 443):
        error_msgs.append(
            _("Value '%s' is not supported for 'irmc_port'.") %
            d_info['irmc_port'])
    if not isinstance(d_info['irmc_client_timeout'], int):
        error_msgs.append(
            _("Value '%s' is not an integer for 'irmc_client_timeout'") %
            d_info['irmc_client_timeout'])
    if d_info['irmc_sensor_method'].lower() not in ('ipmitool', 'scci'):
        error_msgs.append(
            _("Value '%s' is not supported for 'irmc_sensor_method'.") %
            d_info['irmc_sensor_method'])

    verify_ca = utils.get_verify_ca(node, d_info.get('irmc_verify_ca'))
    if verify_ca is None:
        d_info['irmc_verify_ca'] = verify_ca = CONF.webserver_verify_ca

    # Check if verify_ca is a Boolean or a file/directory in the file-system
    if isinstance(verify_ca, str):
        if ((os.path.isdir(verify_ca) and os.path.isabs(verify_ca))
            or (os.path.isfile(verify_ca) and os.path.isabs(verify_ca))):
            # If it's fullpath and dir/file, we don't need to do anything
            pass
        else:
            try:
                d_info['irmc_verify_ca'] = strutils.bool_from_string(
                    verify_ca, strict=True)
            except ValueError:
                error_msgs.append(
                    _('Invalid value type set in driver_info/'
                      'irmc_verify_ca on node %(node)s. '
                      'The value should be a Boolean or the path '
                      'to a file/directory, not "%(value)s"'
                      ) % {'value': verify_ca, 'node': node.uuid})
    elif isinstance(verify_ca, bool):
        # If it's a boolean it's grand, we don't need to do anything
        pass
    else:
        error_msgs.append(
            _('Invalid value type set in driver_info/irmc_verify_ca '
              'on node %(node)s. The value should be a Boolean or the path '
              'to a file/directory, not "%(value)s"') % {'value': verify_ca,
                                                         'node': node.uuid})

    if error_msgs:
        msg = (_("The following errors were encountered while parsing "
                 "driver_info:\n%s") % "\n".join(error_msgs))
        raise exception.InvalidParameterValue(msg)

    d_info.update(_parse_snmp_driver_info(node, info))

    return d_info


def _parse_snmp_driver_info(node, info):
    """Parses the SNMP related driver_info parameters.

    :param node: An Ironic node object.
    :param info: driver_info dictionary.
    :returns: A dictionary containing SNMP information.
    :raises: MissingParameterValue if any of the mandatory
        parameter values are not provided.
    :raises: InvalidParameterValue if there is any invalid
        value provided.
    """
    snmp_info = {param: info.get(param, CONF.irmc.get(param[len('irmc_'):]))
                 for param in SNMP_PROPERTIES}
    valid_versions = {"v1": snmp.SNMP_V1,
                      "v2c": snmp.SNMP_V2C,
                      "v3": snmp.SNMP_V3}

    for int_name, impl_list in INTERFACE_IMPL_LIST_WITH_SNMP.items():
        if getattr(node, int_name) in impl_list:
            break
    else:
        return snmp_info

    if snmp_info['irmc_snmp_version'].lower() not in valid_versions:
        raise exception.InvalidParameterValue(_(
            "Value '%s' is not supported for 'irmc_snmp_version'.") %
            snmp_info['irmc_snmp_version']
        )
    snmp_info["irmc_snmp_version"] = \
        valid_versions[snmp_info["irmc_snmp_version"].lower()]

    snmp_info['irmc_snmp_port'] = utils.validate_network_port(
        snmp_info['irmc_snmp_port'], 'irmc_snmp_port')

    if snmp_info['irmc_snmp_version'] != snmp.SNMP_V3:
        if (snmp_info['irmc_snmp_community']
            and not isinstance(snmp_info['irmc_snmp_community'], str)):
            raise exception.InvalidParameterValue(_(
                "Value '%s' is not a string for 'irmc_snmp_community'") %
                snmp_info['irmc_snmp_community'])
        if utils.is_fips_enabled():
            raise exception.InvalidParameterValue(_(
                "'v3' has to be set for 'irmc_snmp_version' "
                "when FIPS mode is enabled."))

    else:
        snmp_info.update(_parse_snmp_v3_info(node, info))

    return snmp_info


def _parse_snmp_v3_info(node, info):
    snmp_info = {}
    missing_info = []
    valid_values = {'irmc_snmp_auth_proto': ['sha', 'sha256', 'sha384',
                                             'sha512'],
                    'irmc_snmp_priv_proto': ['aes']}
    valid_protocols = {'irmc_snmp_auth_proto': snmp.snmp_auth_protocols,
                       'irmc_snmp_priv_proto': snmp.snmp_priv_protocols}
    snmp_keys = {'irmc_snmp_auth_password', 'irmc_snmp_priv_password'}

    security = info.get('irmc_snmp_security', CONF.irmc.get('snmp_security'))
    for param in SNMP_V3_REQUIRED_PROPERTIES:
        try:
            snmp_info[param] = info[param]
        except KeyError:
            if param == 'irmc_snmp_user':
                if not security:
                    missing_info.append(param)
                else:
                    LOG.warning(_("'irmc_snmp_security' parameter is "
                                  "deprecated in favor of 'irmc_snmp_user' "
                                  "parameter. Please set 'irmc_snmp_user' "
                                  "and remove 'irmc_snmp_security' for node "
                                  "%s."), node.uuid)
                    # In iRMC, the username must start with a letter, so only
                    # a string can be a valid username and a string from a
                    # number is invalid.
                    if not isinstance(security, str):
                        raise exception.InvalidParameterValue(_(
                            "Value '%s' is not a string for "
                            "'irmc_snmp_security.") %
                            info['irmc_snmp_security'])
                    else:
                        snmp_info['irmc_snmp_user'] = security
                        security = None
            else:
                missing_info.append(param)

    if missing_info:
        raise exception.MissingParameterValue(_(
            "The following required SNMP parameters "
            "are missing: %s") % missing_info)

    if security:
        LOG.warning(_("'irmc_snmp_security' parameter is ignored in favor of "
                      "'irmc_snmp_user' parameter. Please remove "
                      "'irmc_snmp_security' from node %s "
                      "configuration."), node.uuid)
    if not isinstance(snmp_info['irmc_snmp_user'], str):
        raise exception.InvalidParameterValue(_(
            "Value '%s' is not a string for 'irmc_snmp_user'.") %
            info['irmc_snmp_user'])

    for param in snmp_keys:
        if not isinstance(snmp_info[param], str):
            raise exception.InvalidParameterValue(_(
                "Value %(value)s is not a string for %(param)s.") %
                {'param': param, 'value': snmp_info[param]})
        if len(snmp_info[param]) < 8:
            raise exception.InvalidParameterValue(_(
                "%s is too short. (8+ chars required)") % param)

    for param in SNMP_V3_OPTIONAL_PROPERTIES:
        value = None
        try:
            value = info[param]
            if value not in valid_values[param]:
                raise exception.InvalidParameterValue(_(
                    "Invalid value %(value)s given for driver info parameter "
                    "%(param)s, the valid values are %(valid_values)s.") %
                    {'param': param,
                     'value': value,
                     'valid_values': valid_values[param]})
        except KeyError:
            value = CONF.irmc.get(param[len('irmc_'):])
        snmp_info[param] = valid_protocols[param].get(value)
        if not snmp_info[param]:
            raise exception.InvalidParameterValue(_(
                "Unknown SNMPv3 protocol %(value)s given for "
                "driver info parameter %(param)s") % {'param': param,
                                                      'value': value})

    return snmp_info


def get_irmc_client(node):
    """Gets an iRMC SCCI client.

    Given an ironic node object, this method gives back a iRMC SCCI client
    to do operations on the iRMC.

    :param node: An ironic node object.
    :returns: scci_cmd partial function which takes a SCCI command param.
    :raises: InvalidParameterValue on invalid inputs.
    :raises: MissingParameterValue if some mandatory information
        is missing on the node
    :raises: IRMCOperationError if iRMC operation failed
    """
    driver_info = parse_driver_info(node)

    scci_client = scci.get_client(
        driver_info['irmc_address'],
        driver_info['irmc_username'],
        driver_info['irmc_password'],
        port=driver_info['irmc_port'],
        auth_method=driver_info['irmc_auth_method'],
        verify=driver_info.get('irmc_verify_ca'),
        client_timeout=driver_info['irmc_client_timeout'])
    return scci_client


def update_ipmi_properties(task):
    """Update ipmi properties to node driver_info.

    :param task: A task from TaskManager.
    """
    node = task.node
    info = node.driver_info

    # updating ipmi credentials
    info['ipmi_address'] = info.get('irmc_address')
    info['ipmi_username'] = info.get('irmc_username')
    info['ipmi_password'] = info.get('irmc_password')

    # saving ipmi credentials to task object
    task.node.driver_info = info


def get_irmc_report(node):
    """Gets iRMC SCCI report.

    Given an ironic node object, this method gives back a iRMC SCCI report.

    :param node: An ironic node object.
    :returns: A xml.etree.ElementTree object.
    :raises: InvalidParameterValue on invalid inputs.
    :raises: MissingParameterValue if some mandatory information
        is missing on the node.
    :raises: scci.SCCIInvalidInputError if required parameters are invalid.
    :raises: scci.SCCIClientError if SCCI failed.
    """
    driver_info = parse_driver_info(node)

    return scci.get_report(
        driver_info['irmc_address'],
        driver_info['irmc_username'],
        driver_info['irmc_password'],
        port=driver_info['irmc_port'],
        auth_method=driver_info['irmc_auth_method'],
        verify=driver_info.get('irmc_verify_ca'),
        client_timeout=driver_info['irmc_client_timeout'])


def get_secure_boot_mode(node):
    """Get the current secure boot mode.

    :param node: An ironic node object.
    :raises: UnsupportedDriverExtension if secure boot is not present.
    :raises: IRMCOperationError if the operation fails.
    """
    driver_info = parse_driver_info(node)

    try:
        return elcm.get_secure_boot_mode(driver_info)
    except elcm.SecureBootConfigNotFound:
        raise exception.UnsupportedDriverExtension(
            driver=node.driver, extension='get_secure_boot_state')
    except scci.SCCIError as irmc_exception:
        LOG.error("Failed to get secure boot for node %s", node.uuid)
        raise exception.IRMCOperationError(
            operation=_("getting secure boot mode"),
            error=irmc_exception)


def set_secure_boot_mode(node, enable):
    """Enable or disable UEFI Secure Boot

    :param node: An ironic node object.
    :param enable: Boolean value. True if the secure boot to be
        enabled.
    :raises: IRMCOperationError if the operation fails.
    """
    driver_info = parse_driver_info(node)

    try:
        elcm.set_secure_boot_mode(driver_info, enable)
        LOG.info("Set secure boot to %(flag)s for node %(node)s",
                 {'flag': enable, 'node': node.uuid})
    except scci.SCCIError as irmc_exception:
        LOG.error("Failed to set secure boot to %(flag)s for node %(node)s",
                  {'flag': enable, 'node': node.uuid})
        raise exception.IRMCOperationError(
            operation=_("setting secure boot mode"),
            error=irmc_exception)


def check_elcm_license(node):
    """Connect to iRMC and return status of eLCM license

    This function connects to iRMC REST API and check whether eLCM
    license is active. This function can be used to check connection to
    iRMC REST API.

    :param node: An ironic node object
    :returns: dictionary whose keys are 'active' and 'status_code'.
        value of 'active' is boolean showing if eLCM license is active
        and value of 'status_code' is int which is HTTP return code
        from iRMC REST API access
    :raises: InvalidParameterValue if invalid value is contained
        in the 'driver_info' property.
    :raises: MissingParameterValue if some mandatory key is missing
        in the 'driver_info' property.
    :raises: IRMCOperationError if the operation fails.
    """
    try:
        d_info = parse_driver_info(node)
        # GET to /rest/v1/Oem/eLCM/eLCMStatus returns
        # JSON data like this:
        #
        # {
        # "eLCMStatus":{
        #      "EnabledAndLicenced":"true",
        #      "SDCardMounted":"false"
        #      }
        # }
        #
        # EnabledAndLicenced tells whether eLCM license is valid
        #
        r = elcm.elcm_request(d_info, 'GET', ELCM_STATUS_PATH)

        # If r.status_code is 200, it means success and r.text is JSON.
        # If it is 500, it means there is problem at iRMC side
        # and iRMC cannot return eLCM status.
        # If it was 401, elcm_request raises SCCIClientError.
        # Otherwise, r.text may not be JSON.
        if r.status_code == 200:
            license_active = strutils.bool_from_string(
                jsonutils.loads(r.text)['eLCMStatus']['EnabledAndLicenced'],
                strict=True)
        else:
            license_active = False

        return {'active': license_active, 'status_code': r.status_code}
    except (scci.SCCIError,
            json.JSONDecodeError,
            TypeError,
            KeyError,
            ValueError) as irmc_exception:
        LOG.error("Failed to check eLCM license status for node $(node)s",
                  {'node': node.uuid})
        raise exception.IRMCOperationError(
            operation='checking eLCM license status',
            error=irmc_exception)


def set_irmc_version(task):
    """Fetch and save iRMC firmware version.

    This function should be called before calling any other functions which
    need to check node's iRMC firmware version.

    Set `<iRMC OS>/<fw version>` to driver_internal_info['irmc_fw_version']

    :param node: An ironic node object
    :raises: InvalidParameterValue if invalid value is contained
        in the 'driver_info' property.
    :raises: MissingParameterValue if some mandatory key is missing
        in the 'driver_info' property.
    :raises: IRMCOperationError if the operation fails.
    :raises: NodeLocked if the target node is already locked.
    """

    node = task.node
    try:
        report = get_irmc_report(node)
        irmc_os, fw_version = scci.get_irmc_version_str(report)

        fw_ver = node.driver_internal_info.get('irmc_fw_version')
        if fw_ver != '/'.join([irmc_os, fw_version]):
            task.upgrade_lock(purpose='saving firmware version')
            node.set_driver_internal_info('irmc_fw_version',
                                          f"{irmc_os}/{fw_version}")
            node.save()
    except scci.SCCIError as irmc_exception:
        LOG.error("Failed to fetch iRMC FW version for node %s",
                  node.uuid)
        raise exception.IRMCOperationError(
            operation=_("fetching irmc fw version "),
            error=irmc_exception)


def _version_lt(v1, v2):
    v1_l = v1.split('.')
    v2_l = v2.split('.')
    if len(v1_l) <= len(v2_l):
        v1_l.extend(['0'] * (len(v2_l) - len(v1_l)))
    else:
        v2_l.extend(['0'] * (len(v1_l) - len(v2_l)))

    for i in range(len(v1_l)):
        if int(v1_l[i]) < int(v2_l[i]):
            return True
        elif int(v1_l[i]) > int(v2_l[i]):
            return False
    else:
        return False


def _version_le(v1, v2):
    v1_l = v1.split('.')
    v2_l = v2.split('.')
    if len(v1_l) <= len(v2_l):
        v1_l.extend(['0'] * (len(v2_l) - len(v1_l)))
    else:
        v2_l.extend(['0'] * (len(v1_l) - len(v2_l)))

    for i in range(len(v1_l)):
        if int(v1_l[i]) < int(v2_l[i]):
            return True
        elif int(v1_l[i]) > int(v2_l[i]):
            return False
    else:
        return True


def within_version_ranges(node, version_ranges):
    """Read saved iRMC FW version and check if it is within the passed ranges.

    :param node: An ironic node object
    :param version_ranges: A Python dictionary containing version ranges in the
        next format: <os_n>: <ranges>, where <os_n> is a string representing
        iRMC OS number (e.g. '4') and <ranges> is a dictionaries indicating
        the specific firmware version ranges under the iRMC OS number <os_n>.

        The dictionary used in <ranges> only has two keys: 'min' and 'upper',
        and value of each key is a string representing iRMC firmware version
        number or None. Both keys can be absent and their value can be None.

        It is acceptable to not set ranges for a <os_n> (for example set
        <ranges> to None, {}, etc...), in this case, this function only
        checks if the node's iRMC OS number matches the <os_n>.

        Valid <version_ranges> example:
            {'3': None,   # all version of iRMC S3 matches
             '4': {},     # all version of iRMC S4 matches
             # all version of iRMC S5 matches
             '5': {'min': None, 'upper': None},
             # iRMC S6 whose version is >=1.20 matches
             '6': {'min': '1.20', 'upper': None},
             # iRMC S7 whose version is
             # 5.51<= (version) <8.23 matches
             '7': {'min': '5.51', 'upper': '8.23'}}

    :returns: True if node's iRMC FW is in range, False if not or
        fails to parse firmware version
    """

    try:
        fw_version = node.driver_internal_info.get('irmc_fw_version', '')
        irmc_os, irmc_ver = fw_version.split('/')

        if IRMC_OS_NAME_R.match(irmc_os) and IRMC_FW_VER_R.match(irmc_ver):
            os_num = IRMC_OS_NAME_NUM_R.search(irmc_os).group(0)
            fw_num = IRMC_FW_VER_NUM_R.search(irmc_ver).group(0)

            if os_num not in version_ranges:
                return False

            v_range = version_ranges[os_num]

            # An OS number with no ranges set means no need to check
            # specific version, all the version under this OS number is valid.
            if not v_range:
                return True

            # Specific range is set, check if the node's
            # firmware version is within it.
            min_ver = v_range.get('min')
            upper_ver = v_range.get('upper')
            flag = True
            if min_ver:
                flag = _version_le(min_ver, fw_num)
            if flag and upper_ver:
                flag = _version_lt(fw_num, upper_ver)
            return flag

    except Exception:
        # All exceptions are ignored
        pass

    LOG.warning('Failed to parse iRMC firmware version on node %(uuid)s: '
                '%(fw_ver)s', {'uuid': node.uuid, 'fw_ver': fw_version})
    return False
