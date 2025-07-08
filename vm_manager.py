import libvirt
import sys
import os
import time
import logging

# --- Script Configuration ---

# VM Details
VM_NAME = "hotplug-test-vm"
# IMPORTANT: Ensure this path points to a bootable OS image (e.g., Ubuntu Cloud Image qcow2)
# The script will warn if it's missing but won't create a bootable OS.
DISK_IMAGE_PATH = "/var/lib/libvirt/images/hotplug-vm.qcow2"
HOTPLUG_DISK_PATH = "/var/lib/libvirt/images/hotplug-disk.qcow2" # Disk for hotplug testing
RAM_MB = 1024  # VM RAM in Megabytes
VCPUS = 1      # Number of virtual CPUs for the VM
HOTPLUG_ITERATIONS = 20 # Number of times to hotplug/unplug the disk

# Libvirt Connection Details
# Use "qemu:///system" for system-wide libvirt daemon (requires root/sudo privileges for the script)
# Use "qemu:///session" for user session libvirt (less privileges needed, VM storage might be in ~/.local/share/libvirt/images)
CONN_URI = "qemu:///system"

# Logging Setup
LOG_FILE = "vm_operations.log" # Name of the log file
logger = logging.getLogger(__name__) # Logger instance

def setup_logging():
    """
    Configures logging to output messages to both the console and a log file.
    - INFO level and above will be logged.
    - Console logs are simpler.
    - File logs include function names for easier debugging.
    """
    logger.setLevel(logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(console_handler)

    # File handler
    try:
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(funcName)s - %(message)s'))
        logger.addHandler(file_handler)
    except IOError as e:
        print(f"Warning: Could not set up log file at '{LOG_FILE}': {e}", file=sys.stderr)

# --- Libvirt and VM Functions ---

def connect_libvirt():
    """Establishes a connection to libvirt."""
    logger.info(f"Attempting to connect to libvirt URI: {CONN_URI}")
    try:
        conn = libvirt.open(CONN_URI)
        if conn is None:
            logger.error(f"Failed to open connection to {CONN_URI}")
            sys.exit(1)
        logger.info(f"Successfully connected to libvirt ({conn.getURI()})")
        return conn
    except libvirt.libvirtError as e:
        logger.error(f"Error connecting to libvirt: {e}")
        sys.exit(1)

def create_vm_xml(vm_name, disk_path, ram_mb, vcpus):
    """Generates the XML definition for a basic KVM VM."""
    # A very basic XML definition.
    # In a real scenario, you'd likely want a more comprehensive definition,
    # potentially loaded from a template file or built more dynamically.
    # This example uses a minimal Ubuntu cloud image as the base.
    # Ensure you have a suitable cloud image at DISK_IMAGE_PATH.
    # For example, download from: https://cloud-images.ubuntu.com/
    xml_desc = f"""
    <domain type='kvm'>
      <name>{vm_name}</name>
      <memory unit='MiB'>{ram_mb}</memory>
      <currentMemory unit='MiB'>{ram_mb}</currentMemory>
      <vcpu placement='static'>{vcpus}</vcpu>
      <os>
        <type arch='x86_64' machine='pc-q35-6.2'>hvm</type>
        <boot dev='hd'/>
      </os>
      <features>
        <acpi/>
        <apic/>
        <vmport desc='off'/>
      </features>
      <cpu mode='host-model' check='partial'/>
      <clock offset='utc'>
        <timer name='rtc' tickpolicy='catchup'/>
        <timer name='pit' tickpolicy='delay'/>
        <timer name='hpet' present='no'/>
      </clock>
      <on_poweroff>destroy</on_poweroff>
      <on_reboot>restart</on_reboot>
      <on_crash>destroy</on_crash>
      <pm>
        <suspend-to-mem enabled='no'/>
        <suspend-to-disk enabled='no'/>
      </pm>
      <devices>
        <emulator>/usr/bin/qemu-system-x86_64</emulator>
        <disk type='file' device='disk'>
          <driver name='qemu' type='qcow2'/>
          <source file='{disk_path}'/>
          <target dev='vda' bus='virtio'/>
        </disk>
        <interface type='network'>
          <mac address='52:54:00:12:34:56'/>
          <source network='default'/>
          <model type='virtio'/>
        </interface>
        <serial type='pty'>
          <target type='isa-serial' port='0'>
            <model name='isa-serial'/>
          </target>
        </serial>
        <console type='pty'>
          <target type='serial' port='0'/>
        </console>
        <input type='tablet' bus='usb'/>
        <input type='keyboard' bus='usb'/>
        <graphics type='vnc' port='-1' autoport='yes' listen='0.0.0.0'>
          <listen type='address' address='0.0.0.0'/>
        </graphics>
        <video>
          <model type='virtio' heads='1' primary='yes'/>
        </video>
        <memballoon model='virtio'/>
        <rng model='virtio'>
          <backend model='random'>/dev/urandom</backend>
        </rng>
      </devices>
    </domain>
    """
    return xml_desc

def define_vm(conn, xml_desc):
    """Defines a VM if it doesn't already exist."""
    try:
        vm = conn.lookupByName(VM_NAME)
        print(f"VM '{VM_NAME}' already defined.")
        return vm
    except libvirt.libvirtError as e:
        if e.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN:
            print(f"Defining VM '{VM_NAME}'...")
            try:
                vm = conn.defineXML(xml_desc)
                if vm is None:
                    print(f"Failed to define VM '{VM_NAME}'", file=sys.stderr)
                    sys.exit(1)
                print(f"VM '{VM_NAME}' defined successfully.")
                return vm
            except libvirt.libvirtError as define_e:
                print(f"Error defining VM: {define_e}", file=sys.stderr)
                sys.exit(1)
        else:
            print(f"Error looking up VM: {e}", file=sys.stderr)
            sys.exit(1)

def start_vm(vm):
    """Starts the VM if it's not already running."""
    if not vm.isActive():
        print(f"Starting VM '{VM_NAME}'...")
        try:
            vm.create()
            # Wait for the VM to boot up a bit
            # This is a simple wait, more robust methods might involve checking guest agent status
            print("Waiting for VM to boot (30 seconds)...")
            time.sleep(30)
            print(f"VM '{VM_NAME}' started.")
        except libvirt.libvirtError as e:
            print(f"Error starting VM: {e}", file=sys.stderr)
            # Attempt to clean up if definition succeeded but start failed
            try:
                if vm.isPersistent(): # Only if it was defined persistently
                    vm.undefine()
            except libvirt.libvirtError:
                pass # Ignore errors during cleanup attempt
            sys.exit(1)
    else:
        print(f"VM '{VM_NAME}' is already running.")

def main():
    """Main function to define and start the VM, then run hotplug tests."""
    conn = None  # Initialize conn to None for the finally block
    try:
        conn = connect_libvirt()

        # Check if the OS disk image exists.
        # For this script, we focus on libvirt interactions, not image creation itself.
        # A real deployment would need a robust way to ensure a bootable OS image.
        if not os.path.exists(DISK_IMAGE_PATH):
            logger.warning(f"OS disk image '{DISK_IMAGE_PATH}' not found.")
            logger.warning("The script will attempt to define the VM, but it will likely not boot or run correctly.")
            logger.warning("Please ensure a bootable OS image (e.g., cloud image) is present at this path for full functionality.")
            # To avoid sandbox issues with os.system for qemu-img, we won't create it here.
            # In a real environment, you might:
            # if not create_os_disk_placeholder(DISK_IMAGE_PATH): # A hypothetical function
            #     logger.critical("Could not ensure OS disk placeholder. Exiting.")
            #     sys.exit(1)

        vm_xml = create_vm_xml(VM_NAME, DISK_IMAGE_PATH, RAM_MB, VCPUS)
        logger.debug(f"Generated VM XML:\n{vm_xml}")

        vm = define_vm(conn, vm_xml)
        if vm is None: # define_vm now handles its own sys.exit on critical failure
            logger.critical("VM definition failed. Exiting.") # Should not be reached if define_vm exits
            sys.exit(1)

        start_vm(vm) # start_vm also handles its own sys.exit

        if vm.isActive():
            logger.info(f"--- Starting Hotplug/Unplug Test Loop ({HOTPLUG_ITERATIONS} iterations) ---")
            hotplug_target_dev = "vdc"
            disk_xml_to_hotplug = create_disk_xml(HOTPLUG_DISK_PATH, hotplug_target_dev)

            for i in range(1, HOTPLUG_ITERATIONS + 1):
                logger.info(f"--- Iteration {i}/{HOTPLUG_ITERATIONS} ---")
                logger.info(f"Attempting to hotplug disk '{HOTPLUG_DISK_PATH}' as '{hotplug_target_dev}'...")
                if hotplug_disk(vm, disk_xml_to_hotplug):
                    logger.info(f"Hotplug iteration {i} successful.")
                    logger.info("Waiting 5 seconds before unplugging...")
                    time.sleep(5)

                    logger.info(f"Attempting to hotunplug disk '{hotplug_target_dev}'...")
                    if hotunplug_disk(vm, disk_xml_to_hotplug):
                        logger.info(f"Hotunplug iteration {i} successful.")
                    else:
                        logger.error(f"Hotunplug iteration {i} failed. Stopping test.")
                        break
                else:
                    logger.error(f"Hotplug iteration {i} failed. Stopping test.")
                    break

                if i < HOTPLUG_ITERATIONS:
                    logger.info("Waiting 2 seconds before next iteration...")
                    time.sleep(2)

            logger.info(f"--- Hotplug/Unplug Test Loop Finished ---")
        else:
            logger.error(f"VM '{VM_NAME}' is not active after start attempt. Skipping hotplug/unplug loop.")

        logger.info(f"Script finished. To cleanup, you might want to manually destroy and undefine the VM: virsh destroy {VM_NAME}; virsh undefine {VM_NAME}")

    except Exception as e:
        logger.critical(f"An unexpected error occurred in main: {e}", exc_info=True)
        sys.exit(1)
    finally:
        if conn:
            try:
                logger.info("Closing libvirt connection.")
                conn.close()
            except libvirt.libvirtError as e:
                logger.error(f"Error closing libvirt connection: {e}")

def create_virtual_disk(disk_path, size_gb=1):
    """Creates a virtual disk image using qemu-img if it doesn't exist."""
    # This script will likely fail to *run* the VM if the disk isn't a bootable OS.
    if not os.path.exists(DISK_IMAGE_PATH):
        print(f"Warning: OS disk image '{DISK_IMAGE_PATH}' not found.")
        print("Attempting to create a placeholder for definition purposes.")
        print("Please ensure a bootable OS image is present at this path to actually run the VM.")
        # Create a small qcow2 file as a placeholder if it doesn't exist
        # This allows defining the VM, but it won't boot properly.
        try:
            os.makedirs(os.path.dirname(DISK_IMAGE_PATH), exist_ok=True)
            # Using qemu-img to create a small disk.
            # This requires qemu-utils to be installed.
            # The user running this script needs permissions to write to DISK_IMAGE_PATH.
            # For the sandbox, we'll assume this won't run directly but serves as the script content.
            # In a real environment, you'd handle this dependency.
            # For now, if qemu-img isn't available or fails, definition might still work
            # if libvirt doesn't strictly check the file at define time.
            # However, VM creation (vm.create()) will fail.
            #
            # For the purpose of this step (Develop VM Boot Script),
            # we are focused on the libvirt interaction part.
            # The actual creation of a bootable image is outside the direct scope of *this* script's logic,
            # though necessary for the VM to fully function.
            #
            # If running locally: sudo apt-get install qemu-utils
            # Create a small (1M) qcow2 image:
            # os.system(f"qemu-img create -f qcow2 {DISK_IMAGE_PATH} 1M")
            #
            # For now, we'll just print a strong warning and proceed.
            # The script's primary goal here is to demonstrate libvirt API usage.
            pass # Not actually creating the image here to avoid sandbox issues.
        except Exception as e:
            print(f"Could not create placeholder disk: {e}", file=sys.stderr)


    vm_xml = create_vm_xml(VM_NAME, DISK_IMAGE_PATH, RAM_MB, VCPUS)
    # print("Generated VM XML:")
    # print(vm_xml)

    vm = define_vm(conn, vm_xml)
    start_vm(vm)

    if vm.isActive():
        print(f"\n--- Starting Hotplug/Unplug Test Loop (20 iterations) ---")
        hotplug_target_dev = "vdc" # Consistently use 'vdc' for this test disk
        disk_xml_to_hotplug = create_disk_xml(HOTPLUG_DISK_PATH, hotplug_target_dev)

        for i in range(1, 21):
            print(f"\n--- Iteration {i}/20 ---")

            print(f"Attempting to hotplug disk '{HOTPLUG_DISK_PATH}' as '{hotplug_target_dev}'...")
            if hotplug_disk(vm, disk_xml_to_hotplug):
                print(f"Hotplug iteration {i} successful.")
                print("Waiting 5 seconds before unplugging...")
                time.sleep(5)

                print(f"Attempting to hotunplug disk '{hotplug_target_dev}'...")
                if hotunplug_disk(vm, disk_xml_to_hotplug): # Use the same XML for detach
                    print(f"Hotunplug iteration {i} successful.")
                else:
                    print(f"Hotunplug iteration {i} failed. Stopping test.", file=sys.stderr)
                    break # Exit loop on failure
            else:
                print(f"Hotplug iteration {i} failed. Stopping test.", file=sys.stderr)
                break # Exit loop on failure

            if i < 20: # Don't wait after the last iteration's unplug
                print("Waiting 2 seconds before next iteration...")
                time.sleep(2)

        print(f"\n--- Hotplug/Unplug Test Loop Finished ---")
    else:
        print(f"VM '{VM_NAME}' is not active. Skipping hotplug/unplug loop.", file=sys.stderr)


    print(f"\nTo cleanup, you might want to manually destroy and undefine the VM: virsh destroy {VM_NAME}; virsh undefine {VM_NAME}")
    conn.close()

def create_virtual_disk(disk_path, size_gb=1):
    """Creates a virtual disk image using qemu-img if it doesn't exist."""
    if os.path.exists(disk_path):
        print(f"Disk image '{disk_path}' already exists.")
        return True

    print(f"Creating virtual disk '{disk_path}' of size {size_gb}GB...")
    try:
        os.makedirs(os.path.dirname(disk_path), exist_ok=True)
        # Ensure qemu-img is installed and accessible in PATH
        ret = os.system(f"qemu-img create -f qcow2 {disk_path} {size_gb}G")
        if ret == 0:
            print(f"Disk image '{disk_path}' created successfully.")
            return True
        else:
            print(f"Failed to create disk image '{disk_path}'. qemu-img command failed with exit code {ret}.", file=sys.stderr)
            return False
    except Exception as e:
        print(f"Error creating disk image '{disk_path}': {e}", file=sys.stderr)
        return False

def create_disk_xml(disk_file_path, target_dev):
    """Generates XML for a disk to be hotplugged."""
    # Ensure the disk is using virtio for better performance and hotplug capability
    xml = f"""
    <disk type='file' device='disk'>
      <driver name='qemu' type='qcow2'/>
      <source file='{disk_file_path}'/>
      <target dev='{target_dev}' bus='virtio'/>
    </disk>
    """
    # print(f"Generated disk XML for {target_dev}:\n{xml}")
    return xml

def hotplug_disk(vm, disk_xml):
    """Hotplugs a disk to the VM."""
    if not vm.isActive():
        print(f"VM '{vm.name()}' is not running. Cannot hotplug disk.", file=sys.stderr)
        return False
    try:
        print(f"Attaching disk to '{vm.name()}'...")
        # VIR_DOMAIN_DEVICE_MODIFY_LIVE: Affect running domain state.
        # VIR_DOMAIN_DEVICE_MODIFY_CONFIG: Affect persistent domain state (if VM is persistent).
        # For hotplug, typically you want VIR_DOMAIN_AFFECT_LIVE.
        # If you also want it to persist across reboots of a persistent VM, add VIR_DOMAIN_AFFECT_CONFIG.
        # For this example, we'll make it live only.
        vm.attachDeviceFlags(disk_xml, libvirt.VIR_DOMAIN_DEVICE_MODIFY_LIVE)
        print("Disk attached successfully (live).")
        return True
    except libvirt.libvirtError as e:
        print(f"Error attaching disk: {e}", file=sys.stderr)
        return False

def hotunplug_disk(vm, disk_xml):
    """Hotunplugs a disk from the VM."""
    if not vm.isActive():
        print(f"VM '{vm.name()}' is not running. Cannot hotunplug disk.", file=sys.stderr)
        return False
    try:
        print(f"Detaching disk from '{vm.name()}'...")
        vm.detachDeviceFlags(disk_xml, libvirt.VIR_DOMAIN_DEVICE_MODIFY_LIVE)
        print("Disk detached successfully (live).")
        return True
    except libvirt.libvirtError as e:
        print(f"Error detaching disk: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    # Create the hotpluggable disk image first if it doesn't exist
    if not create_virtual_disk(HOTPLUG_DISK_PATH, size_gb=1):
        print(f"Exiting because hotplug disk '{HOTPLUG_DISK_PATH}' could not be created.", file=sys.stderr)
        sys.exit(1)
    main()
