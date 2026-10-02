"""Register the fake OTAA device with gateway-hello's ChirpStack.

Compared with ABP there is no activation step: the network only needs the
device's root key, and the session is created when the device joins.

    gateway -> device profile -> application -> device -> device keys

Run it once after gateway-hello's `docker compose up`; running it again is
harmless.

    uv run provision.py
"""

import grpc
from chirpstack_api import api, common

from common import (
    APP_EUI,
    APP_KEY,
    CHIRPSTACK_API,
    CHIRPSTACK_PASSWORD,
    CHIRPSTACK_USER,
    DEV_EUI,
    GATEWAY_ID,
)

DEVICE_PROFILE_NAME = "OTAA, Class A, AS923"
APPLICATION_NAME = "hello"  # the same application as gateway-hello's device


def exists(get, request, auth) -> bool:
    try:
        get(request, metadata=auth)
    except grpc.RpcError as err:
        if err.code() == grpc.StatusCode.NOT_FOUND:
            return False
        raise
    return True


def find(items, name: str):
    return next((item.id for item in items if item.name == name), None)


def main() -> None:
    channel = grpc.insecure_channel(CHIRPSTACK_API)

    login = api.InternalServiceStub(channel).Login(
        api.LoginRequest(email=CHIRPSTACK_USER, password=CHIRPSTACK_PASSWORD)
    )
    auth = [("authorization", f"Bearer {login.jwt}")]

    tenants = api.TenantServiceStub(channel).List(api.ListTenantsRequest(limit=10), metadata=auth)
    tenant_id = tenants.result[0].id
    print(f"[provision] tenant {tenants.result[0].name} ({tenant_id})")

    gateways = api.GatewayServiceStub(channel)
    if exists(gateways.Get, api.GetGatewayRequest(gateway_id=GATEWAY_ID), auth):
        print(f"[provision] gateway {GATEWAY_ID} already exists")
    else:
        gateways.Create(
            api.CreateGatewayRequest(
                gateway=api.Gateway(
                    gateway_id=GATEWAY_ID,
                    name="fake-gateway",
                    tenant_id=tenant_id,
                    stats_interval=30,
                )
            ),
            metadata=auth,
        )
        print(f"[provision] gateway {GATEWAY_ID} created")

    profiles = api.DeviceProfileServiceStub(channel)
    listed = profiles.List(
        api.ListDeviceProfilesRequest(tenant_id=tenant_id, limit=100), metadata=auth
    )
    profile_id = find(listed.result, DEVICE_PROFILE_NAME)
    if profile_id is None:
        profile_id = profiles.Create(
            api.CreateDeviceProfileRequest(
                device_profile=api.DeviceProfile(
                    tenant_id=tenant_id,
                    name=DEVICE_PROFILE_NAME,
                    region=common.Region.AS923,
                    region_config_id="as923",
                    mac_version=common.MacVersion.LORAWAN_1_0_3,
                    reg_params_revision=common.RegParamsRevision.A,
                    adr_algorithm_id="default",
                    supports_otaa=True,
                    uplink_interval=60,
                )
            ),
            metadata=auth,
        ).id
        print(f"[provision] device profile created ({profile_id})")

    applications = api.ApplicationServiceStub(channel)
    listed = applications.List(
        api.ListApplicationsRequest(tenant_id=tenant_id, limit=100), metadata=auth
    )
    application_id = find(listed.result, APPLICATION_NAME)
    if application_id is None:
        application_id = applications.Create(
            api.CreateApplicationRequest(
                application=api.Application(tenant_id=tenant_id, name=APPLICATION_NAME)
            ),
            metadata=auth,
        ).id
        print(f"[provision] application created ({application_id})")

    devices = api.DeviceServiceStub(channel)
    if exists(devices.Get, api.GetDeviceRequest(dev_eui=DEV_EUI), auth):
        print(f"[provision] device {DEV_EUI} already exists")
    else:
        devices.Create(
            api.CreateDeviceRequest(
                device=api.Device(
                    dev_eui=DEV_EUI,
                    name="otaa-device",
                    application_id=application_id,
                    device_profile_id=profile_id,
                    join_eui=APP_EUI,
                )
            ),
            metadata=auth,
        )
        print(f"[provision] device {DEV_EUI} created")

    if exists(devices.GetKeys, api.GetDeviceKeysRequest(dev_eui=DEV_EUI), auth):
        print("[provision] device keys already set")
    else:
        # A LoRaWAN 1.0.x AppKey goes in nwk_key, not app_key: in 1.1 the
        # single root key was split in two, and ChirpStack names the fields
        # after 1.1.
        devices.CreateKeys(
            api.CreateDeviceKeysRequest(
                device_keys=api.DeviceKeys(dev_eui=DEV_EUI, nwk_key=APP_KEY)
            ),
            metadata=auth,
        )
        print("[provision] device keys set")
    print(f"[provision] application {APPLICATION_NAME} is {application_id}")


if __name__ == "__main__":
    main()
