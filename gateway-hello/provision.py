"""Register the fake gateway and device with ChirpStack.

A real network server ignores gateways and devices it does not know, so they
have to be registered first, just as you would in the web UI:

    gateway -> device profile -> application -> device -> ABP activation

Run it once after `docker compose up`; running it again is harmless.

    uv run provision.py
    uv run provision.py --reactivate   # reset the frame counters on both sides
"""

import argparse
import os

import grpc
from chirpstack_api import api, common

from common import (
    APP_S_KEY,
    CHIRPSTACK_API,
    CHIRPSTACK_PASSWORD,
    CHIRPSTACK_USER,
    DEV_ADDR,
    DEV_EUI,
    GATEWAY_ID,
    STATE_FILE,
    NWK_S_KEY,
)

DEVICE_PROFILE_NAME = "ABP, Class A, AS923"
APPLICATION_NAME = "hello"


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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reactivate",
        action="store_true",
        help="activate the device again, resetting its frame counters",
    )
    args = parser.parse_args()

    channel = grpc.insecure_channel(CHIRPSTACK_API)

    # Log in like the web UI does and use the session token for every call.
    # A real integration would create an API key instead.
    login = api.InternalServiceStub(channel).Login(
        api.LoginRequest(email=CHIRPSTACK_USER, password=CHIRPSTACK_PASSWORD)
    )
    auth = [("authorization", f"Bearer {login.jwt}")]

    tenants = api.TenantServiceStub(channel).List(api.ListTenantsRequest(limit=10), metadata=auth)
    tenant_id = tenants.result[0].id  # the default "ChirpStack" tenant
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
                    supports_otaa=False,
                    uplink_interval=60,
                    # An ABP device never receives these in a join accept, so
                    # the network has to be told what the device uses.
                    abp_rx1_delay=1,
                    abp_rx1_dr_offset=0,
                    abp_rx2_dr=2,
                    abp_rx2_freq=923_200_000,
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
    device = api.Device(
        dev_eui=DEV_EUI,
        name="hello-device",
        application_id=application_id,
        device_profile_id=profile_id,
    )
    if exists(devices.Get, api.GetDeviceRequest(dev_eui=DEV_EUI), auth):
        print(f"[provision] device {DEV_EUI} already exists")
    else:
        devices.Create(api.CreateDeviceRequest(device=device), metadata=auth)
        print(f"[provision] device {DEV_EUI} created")
        args.reactivate = True

    # Activating resets the frame counters ChirpStack expects, so only do it
    # for a new device or when asked -- and then the device has to start from
    # 0 as well.
    if args.reactivate:
        activate(devices, auth)
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
    print(f"[provision] application {APPLICATION_NAME} is {application_id}")


def activate(devices: api.DeviceServiceStub, auth) -> None:
    # LoRaWAN 1.0.x has one network session key; ChirpStack stores it in all
    # three 1.1 slots.
    devices.Activate(
        api.ActivateDeviceRequest(
            device_activation=api.DeviceActivation(
                dev_eui=DEV_EUI,
                dev_addr=DEV_ADDR,
                app_s_key=APP_S_KEY,
                nwk_s_enc_key=NWK_S_KEY,
                s_nwk_s_int_key=NWK_S_KEY,
                f_nwk_s_int_key=NWK_S_KEY,
            )
        ),
        metadata=auth,
    )
    print(f"[provision] device activated with DevAddr {DEV_ADDR}, frame counters at 0")


if __name__ == "__main__":
    main()
