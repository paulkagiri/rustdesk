# Camera and microphone bridge

This helper sends a controller Mac's camera and microphone through an existing RustDesk desktop session to a remote Windows PC or Apple silicon Mac. It uses only local connections to RustDesk on each computer. The remote app must select the virtual camera and microphone; this helper does not change system defaults.

## Set up both computers

1. Install a build of this fork on both computers. Standard RustDesk builds do not include this bridge. The **Windows fork build** and **macOS fork build** GitHub Actions workflows provide test builds. Choose the `aarch64` macOS build for Apple silicon.
2. Install 64-bit Python 3.11 through 3.14 on both computers. Use a native Apple silicon build on an Apple silicon Mac. The commands below use 3.11; change that to your installed version if needed. Run them from the repository root. If you copied only `tools/device_media`, enter that folder and skip the `cd` command.

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

3. Install virtual devices on the **remote** computer only:
   - **Windows:** Install [OBS Studio](https://obsproject.com/download) and [VB-CABLE](https://vb-audio.com/Cable/index.htm). For VB-CABLE, extract the download, run its setup program as administrator and restart Windows. Run `devices` again, then set `AUDIO_OUTPUT_DEVICE` in `.env` to the index of the **CABLE Input** playback device (an entry with output channels).
   - **macOS:** Install [OBS Studio 30 or later](https://obsproject.com/download) and [BlackHole 2ch](https://github.com/ExistentialAudio/BlackHole). If prompted, approve OBS's camera extension. Start and stop OBS Virtual Camera once, then quit OBS. Set `AUDIO_OUTPUT_DEVICE=BlackHole 2ch` in `.env`.

On the **controller**, `CAMERA_INDEX=0` and a blank `MIC_INPUT_DEVICE` use the first camera and default microphone. Change them if needed. On macOS, allow camera and microphone access for the terminal or Python when prompted.

## Quick test

1. On the remote computer, run `receive` from `tools/device_media` in the signed-in desktop session:

   ```sh
   .venv/bin/python -m device_media receive
   ```

   On Windows, run `.\.venv\Scripts\python.exe -m device_media receive` instead.
2. On the controller, run `.venv/bin/python -m device_media capture` from the same folder.
3. Connect with RustDesk using a normal desktop session. If already connected, disconnect and reconnect. Both terminals should report `Desktop session connected`.
4. In an app on the remote computer, select **OBS Virtual Camera**. For its microphone, select **CABLE Output** on Windows or **BlackHole 2ch** on macOS. Check the camera preview and microphone input meter. Reopen the app if the new devices do not appear.

For a camera-only test, add `--no-audio` to both helper commands. For a microphone-only test, add `--no-video`. Stop either helper with Ctrl+C. OBS's own virtual camera must be stopped while `receive` runs. If audio is missing, check the exact playback device name printed by `devices` and the helper's terminal output.

If the desktop becomes slow when video starts, set `CAMERA_FPS=3` and `JPEG_QUALITY=30` in the controller's `.env`. Restart `capture`, then reconnect the desktop session. Stop `capture` during a slow session to check whether the camera stream is the cause.
