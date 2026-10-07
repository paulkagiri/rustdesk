# Camera and microphone over a desktop session

This optional bridge makes the controller's camera and microphone available to apps on a remote Windows or Apple silicon Mac. Media travels inside the authenticated RustDesk desktop connection. The helpers listen only on `127.0.0.1` on their own computers. They do not open another network connection between computers.

The current build uses installed virtual devices. On the remote computer, apps select **OBS Virtual Camera** for video and the virtual cable's **recording/input** device for audio. RustDesk itself does not install those devices.

## One-time setup

1. Install a build of this fork on **both** computers. The controller and remote host must both include `DeviceMediaFrame` support. Start a normal remote desktop session, not a file transfer or camera-view session.
2. Install 64-bit Python 3.11 or 3.12 on each computer. Use a native Apple silicon Python on an M-series Mac.
3. On each computer, set up this helper in `tools/device_media`:

   **macOS**

   ```sh
   cd tools/device_media
   python3.11 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   cp .env.example .env
   .venv/bin/python -m device_media devices
   ```

   **Windows PowerShell**

   ```powershell
   cd tools\device_media
   py -3.11 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   Copy-Item .env.example .env
   .\.venv\Scripts\python.exe -m device_media devices
   ```

4. On a **remote Windows** computer, install [OBS Studio](https://obsproject.com/download) for its virtual camera and [VB-CABLE](https://vb-audio.com/Cable/index.htm) for its virtual microphone. Set `AUDIO_OUTPUT_DEVICE` in the helper's `.env` to the **CABLE Input** playback device shown by `devices`. Remote apps then choose **CABLE Output** as their microphone.
5. On a **remote Mac**, install [OBS Studio 30 or later](https://obsproject.com/download) and [BlackHole 2ch](https://github.com/ExistentialAudio/BlackHole). Approve OBS's camera extension in System Settings if macOS asks. Open OBS once, start and stop its virtual camera, then quit OBS. Set `AUDIO_OUTPUT_DEVICE=BlackHole 2ch` in `.env`. Remote apps choose **BlackHole 2ch** as their microphone.
6. On the **controller Mac**, choose `CAMERA_INDEX` and `MIC_INPUT_DEVICE` in `.env`. A blank microphone value uses the default input. Grant camera and microphone permission to the terminal or Python process when macOS asks.

The remote helper deliberately ignores audio until `AUDIO_OUTPUT_DEVICE` is set. It never sends microphone audio to the remote computer's speakers by default.

## Run

Start the remote helper in a terminal in the signed-in user's session before connecting:

```sh
.venv/bin/python -m device_media receive
```

On Windows, use `.\.venv\Scripts\python.exe -m device_media receive` instead. Start the controller helper on the Mac:

```sh
.venv/bin/python -m device_media capture
```

Then connect with RustDesk. Capture starts after the remote desktop login succeeds. The remote helper feeds the virtual devices once it receives media. Select **OBS Virtual Camera** and the virtual cable's recording device in the remote app. If an app was already open, refresh its device list or reopen it.

Use `--no-audio` or `--no-video` on either helper to run one device only. Stop a helper with Ctrl+C. Disconnecting RustDesk closes both local media sockets; the controller helper stops opening the camera and microphone and waits for the next session.

## Limits and checks

- Video is 640 × 480 JPEG at up to 10 frames per second. Audio is 48 kHz mono PCM. The bridge drops excess frames when the connection or a virtual device falls behind.
- Virtual camera and cable devices must be installed separately on each remote computer. This fork does not bundle OBS, VB-CABLE or BlackHole.
- A virtual camera can normally be driven by only one process at a time. Stop OBS's own virtual camera before running `receive`.
- Run `python -m device_media devices` and use the exact playback device name or index if the audio helper cannot open its output. Check the helper's terminal output for camera permission and device errors.
- Both RustDesk ends need this fork's protocol change. With an older remote build, the controller helper remains idle.
- One controller helper feeds one desktop session at a time. Close that session before connecting to another host with the same camera and microphone.

The OBS and audio-device setup follows the [pyvirtualcam instructions](https://github.com/letmaik/pyvirtualcam), [OBS camera extension guide](https://obsproject.com/kb/virtual-camera-troubleshooting), [VB-CABLE device naming](https://vb-audio.com/Cable/index.htm) and [BlackHole documentation](https://github.com/ExistentialAudio/BlackHole).
