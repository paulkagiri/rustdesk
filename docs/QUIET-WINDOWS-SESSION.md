# Quiet Windows sessions

This fork starts from RustDesk 1.5.0. It restores the **Hide connection management window** setting for all desktop clients. That setting only works when incoming sessions require a permanent password. This fork also hides the tray icon by default on all desktop clients. The RustDesk service keeps running after you close the main window. These source changes are shared across platforms, although the workflow below builds only Windows x64.

## Build on GitHub

Open **Actions → Windows fork build → Run workflow** on this fork. The run builds the Windows x64 client and uploads `rustdesk-windows-x64-installers` as an artifact. Download that artifact from the completed run to get the EXE and MSI installers. These installers are unsigned.

The workflow builds from this fork's source on GitHub. It does not publish a GitHub release or need signing secrets.

## Set up on a Windows device

1. Install the MSI from the artifact and confirm the RustDesk service is running in Windows Services.
2. In **Settings → Security → Password**, set **Accept sessions via password** and **Use permanent password**. Set a permanent password.
3. Select **Hide connection management window**.
4. Close the RustDesk main window. Check that its taskbar button and tray icon disappear while the service remains running.
5. Connect from another RustDesk client using your preferred connection method. Check that the connection manager does not interrupt the Windows desktop or appear on the taskbar.
6. Test a disconnect, reconnect and Windows restart before relying on unattended access. Disconnect from the remote client, or stop the RustDesk service locally in Windows Services.

RustDesk's main window still appears on the taskbar when you open it yourself. A signed custom-client configuration can set `hide-tray` to `N` to restore the tray icon. The build does not change how connections are configured.
