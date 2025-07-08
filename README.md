# Virtual Machine Hotplug Test Script

This script uses `libvirt-python` to manage a KVM virtual machine, specifically to test disk hotplug and hotunplug functionality. It will:
1.  Define and start a test VM (if not already defined/running).
2.  Create a separate virtual disk image for hotplugging (if it doesn't exist).
3.  Repeatedly attach (hotplug) and detach (hotunplug) the virtual disk to the running VM.

Logs of operations are printed to the console and saved to `vm_operations.log`.

## Prerequisites

### 1. Operating System and Virtualization Support
*   A Linux system with KVM (Kernel-based Virtual Machine) support.
    *   Ensure your CPU supports virtualization (Intel VT-x or AMD-V) and it's enabled in the BIOS/UEFI.
    *   Verify KVM modules are loaded: `lsmod | grep kvm` (should show `kvm_intel` or `kvm_amd`).

### 2. Install Dependencies
You'll need Python 3, libvirt, QEMU, and associated development libraries/tools.

**On Debian/Ubuntu-based systems:**
```bash
sudo apt update
sudo apt install -y python3 python3-pip qemu-kvm libvirt-daemon-system libvirt-clients bridge-utils virt-manager qemu-utils
sudo pip3 install libvirt-python
```

**On Fedora/RHEL-based systems:**
```bash
sudo dnf install -y python3 python3-pip qemu-kvm libvirt-daemon libvirt-client libvirt-daemon-kvm bridge-utils virt-install qemu-img
sudo pip3 install libvirt-python
```

### 3. Libvirt Daemon
Ensure the `libvirtd` service is running and enabled:
```bash
sudo systemctl start libvirtd
sudo systemctl enable libvirtd
sudo systemctl status libvirtd
```

### 4. User Permissions
*   The script is configured to use the system-wide libvirt daemon (`qemu:///system`). Running the script will likely require `sudo` or for your user to be part of the `libvirt` or `kvm` group.
    ```bash
    sudo usermod -aG libvirt $(whoami)
    sudo usermod -aG kvm $(whoami)
    ```
    You may need to log out and log back in for group changes to take effect.
*   The script attempts to create disk images in `/var/lib/libvirt/images/`. Ensure the user running the script has write permissions to this directory, or change `DISK_IMAGE_PATH` and `HOTPLUG_DISK_PATH` in the script to a location where you have permissions.

### 5. Default Network
The default VM XML uses `<source network='default'/>`. Ensure the libvirt default network is active:
```bash
virsh net-list
virsh net-start default # If not active
virsh net-autostart default # To make it persistent
```

### 6. Base OS Image for VM
*   The script expects a bootable OS disk image for the main VM at the path specified by `DISK_IMAGE_PATH` (default: `/var/lib/libvirt/images/hotplug-vm.qcow2`).
*   A common choice is an Ubuntu Cloud Image. You can download one from [https://cloud-images.ubuntu.com/](https://cloud-images.ubuntu.com/).
    *   Example (for Ubuntu 22.04 LTS "Jammy Jellyfish"):
        ```bash
        # Create the directory if it doesn't exist
        sudo mkdir -p /var/lib/libvirt/images/
        # Download the image
        sudo wget https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img -O /var/lib/libvirt/images/hotplug-vm.qcow2
        ```
    *   **Note**: Cloud images often require cloud-init for proper setup (like setting a default user/password). The basic XML in this script does not include cloud-init configuration. For interactive use, you might need to customize the image or use a different type of installation media. For non-interactive testing of hotplug, a non-booting VM might still allow libvirt operations, but the guest OS won't be running.
*   If this base OS image is not present, the script will log a warning. The VM definition might succeed, but the VM will not boot into a functional OS.

## Running the Script

1.  **Configure Paths (if necessary)**:
    *   Edit `vm_manager.py` and adjust `DISK_IMAGE_PATH` and `HOTPLUG_DISK_PATH` if you are not using `/var/lib/libvirt/images/` or if your base OS image has a different name.
    *   Adjust `CONN_URI` if you want to use `qemu:///session` (user session) instead of `qemu:///system`.

2.  **Execute the script**:
    ```bash
    # If using qemu:///system (default)
    sudo python3 vm_manager.py

    # If you configured for qemu:///session and have permissions set up
    # python3 vm_manager.py
    ```

## Script Overview

*   **`vm_manager.py`**:
    *   **Configuration**: Sets VM name, disk paths, RAM, vCPUs, libvirt URI, and log file name.
    *   **`setup_logging()`**: Configures logging to console and `vm_operations.log`.
    *   **`connect_libvirt()`**: Connects to the libvirt daemon.
    *   **`create_vm_xml()`**: Generates XML for the base VM.
    *   **`define_vm()`**: Defines the VM in libvirt.
    *   **`start_vm()`**: Starts the VM.
    *   **`create_virtual_disk()`**: Creates the `.qcow2` disk image for hotplugging using `qemu-img`.
    *   **`create_disk_xml()`**: Generates XML for the disk to be hotplugged.
    *   **`hotplug_disk()`**: Attaches the disk to the running VM.
    *   **`hotunplug_disk()`**: Detaches the disk from the VM.
    *   **`main()`**: Orchestrates the setup, VM start, and the hotplug/unplug loop.

## Expected Behavior

*   The script will output logs to the console.
*   A more detailed log will be written to `vm_operations.log` in the same directory as the script.
*   A VM named "hotplug-test-vm" will be defined and started.
*   A disk image `hotplug-disk.qcow2` will be created (if it doesn't exist).
*   The script will then loop 20 times, attempting to:
    1.  Hotplug `hotplug-disk.qcow2` (usually as `/dev/vdc` inside the guest).
    2.  Wait for 5 seconds.
    3.  Hotunplug the disk.
    4.  Wait for 2 seconds before the next iteration.
*   If any hotplug or hotunplug operation fails, the loop will terminate.

## Troubleshooting

*   **Permission Errors**:
    *   Ensure your user is in the `libvirt` and `kvm` groups if not running with `sudo`.
    *   Check write permissions for `/var/lib/libvirt/images/` (or your configured disk paths) and for `vm_operations.log`.
*   **Libvirt Connection Failed**:
    *   Verify `libvirtd` service is running (`sudo systemctl status libvirtd`).
    *   Check if `CONN_URI` in the script is correct for your setup.
*   **`qemu-img` not found**:
    *   Ensure `qemu-utils` (or the equivalent package for your distribution) is installed and `qemu-img` is in your system's PATH.
*   **VM fails to start**:
    *   Ensure `DISK_IMAGE_PATH` points to a valid, bootable OS image.
    *   Check libvirt logs for more details: `sudo journalctl -u libvirtd` or logs in `/var/log/libvirt/qemu/`.
*   **Hotplug/Unplug Failures**:
    *   These can sometimes occur if the guest OS is very busy or if there are issues with virtio drivers in the guest. The logs (`vm_operations.log` and guest dmesg) might provide clues.
    *   Ensure the VM has had enough time to boot before hotplug operations begin (the script waits 30 seconds by default).

## Cleaning Up
After the script runs, the VM ("hotplug-test-vm") will be left running (or defined if it failed to start). The disk images will also remain.
To manually clean up:
```bash
# If the VM is running
sudo virsh destroy hotplug-test-vm

# Undefine the VM configuration
sudo virsh undefine hotplug-test-vm

# Remove the disk images (optional)
sudo rm /var/lib/libvirt/images/hotplug-vm.qcow2
sudo rm /var/lib/libvirt/images/hotplug-disk.qcow2
```
Adjust paths if you changed them in the script.
