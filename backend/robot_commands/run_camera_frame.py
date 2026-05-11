import importlib
import os
import sys
import time


def load_symbol(import_spec: str):
    module_name, separator, attr_name = import_spec.partition(":")
    if not module_name or not separator or not attr_name:
        raise ValueError(
            "UNITREE_CAMERA_CLIENT_IMPORT must look like "
            "'package.module:ClassName'"
        )

    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 run_camera_frame.py <interface>", file=sys.stderr)
        return 1

    iface = sys.argv[1]
    domain_id = int(os.getenv("UNITREE_CAMERA_DOMAIN_ID", "0"))
    timeout_s = float(os.getenv("UNITREE_CAMERA_TIMEOUT", "5"))
    client_import = os.getenv(
        "UNITREE_CAMERA_CLIENT_IMPORT",
        "unitree_sdk2py.go2.video.video_client:VideoClient",
    )

    from unitree_sdk2py.core.channel import ChannelFactoryInitialize

    VideoClient = load_symbol(client_import)

    ChannelFactoryInitialize(domain_id, iface)

    client = VideoClient()
    if hasattr(client, "SetTimeout"):
        client.SetTimeout(timeout_s)
    client.Init()

    code = -1
    payload = b""

    for _ in range(6):
        code, data = client.GetImageSample()
        if code == 0 and data:
            payload = bytes(data)
            if payload:
                sys.stdout.buffer.write(payload)
                sys.stdout.buffer.flush()
                return 0
        time.sleep(0.1)

    print(f"GetImageSample failed with code={code}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
