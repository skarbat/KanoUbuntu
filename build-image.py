#!/usr/bin/env python
#
#  build-image.py - Expand Ubuntu Mate for RaspberryPI 2 with KanoOS software
#
#  The process uses xsysroot to create a new Ubuntu image with KanoOS software:
#
#   1. Takes the Ubuntu image and expands it to fit a 4GB SD card
#   2. Installs KanoOS software
#   3. Converts the final image ready to flash and boot
#
#  Each time this tools is invoked, a fresh Ubuntu image will be used from scratch.
#
#  One of the following options must be provided through the command line:
#
#   --prepare-only" Will take Ubuntu image, expand, and make KanoOS software available to install.
#   --build-all" Option above, install KanoOS apps and convert image ready to flash.
#

import os
import sys
import time

__version__='0.7'

def import_xsysroot():
    '''
    Find path to XSysroot and import it
    You need to create a symlink xsysroot.py -> xsysroot
    '''
    which_xsysroot=os.popen('which xsysroot').read().strip()
    if not which_xsysroot:
        print 'Could not find xsysroot tool'
        print 'Please install from https://github.com/skarbat/xsysroot'
        return None
    else:
        print 'xsysroot found at: {}'.format(which_xsysroot)
        sys.path.append(os.path.dirname(which_xsysroot))
        import xsysroot
        return xsysroot

def fix_videocore_permissions(xubuntu, group='adm'):
    '''
    Adds a Udev rule to allow a system users group to access to RaspberryPI GPU
    You will need to do this after your first Ubuntu user creation: $ usermod -aG video USERNAME
    '''
    udev_rule='SUBSYSTEM=="vchiq",GROUP="{}",MODE="0660"'.format(group)
    udev_file='/etc/udev/rules.d/10-vchiq-permissions.rules'
    xubuntu.execute('/bin/bash -c "printf \'{}\' > {}"'.format(udev_rule, udev_file))

if __name__ == '__main__':

    kano_dependencies='libimlib2 python-docopt' # FIXME: These are actually missing dependencies
    extra_packages='openssh-server'
    kano_packages='{} {} kdesk kdesk-dbg kano-screenshot make-minecraft make-pong linux-story'.format(kano_dependencies, extra_packages)
    kano_pip_packages='' # TODO: It will be needed when more Kano software is installed

    kanubuntu_image='UbuntuKanux-{}.img'.format(__version__)
    prepare_only=False

    # Xsysroot profile name that holds the original UbuntuOS for the RPI
    # (See the file xsysroot.conf for details)
    xsysroot_profile_name='kanoubuntu'

    # --dry-run will not install any software, but expand the image
    if len(sys.argv) > 1:
        if sys.argv[1] == '--prepare-only':
            prepare_only=True
            print 'Running in --prepare-only mode'
        elif sys.argv[1] == '--build-all':
            print 'Running in --build-all mode'
        else:
            print 'Unrecognized option, use one of --build-all or --prepare-only'
            sys.exit(1)
    else:
        print 'Please specify mode: --build-all or --prepare-only'
        sys.exit(1)

    # import the xsysroot module which will help us manipulate the Ubuntu image
    xsysroot=import_xsysroot()
    if not xsysroot:
        sys.exit(1)

    # Find and activate the ubuntu xsysroot profile
    try:
        Xubuntu=xsysroot.XSysroot(profile=xsysroot_profile_name)
    except:
        print 'You need to create a Xsysroot ubuntu profile'
        print 'Please see the README file'
        sys.exit(1)

    # start timer
    time_start=time.time()

    # make sure the image is not mounted, or currently in use
    if Xubuntu.is_mounted():
        if not Xubuntu.umount():
            sys.exit(1)

    # renew the Ubuntu image from scratch and expand to root file system
    if not Xubuntu.renew():
        sys.exit(1)
    else:
        Xubuntu.umount()
        if not Xubuntu.expand():
            sys.exit(1)
        else:
            if not Xubuntu.mount():
                sys.exit(1)

    # Paths to add KanoOS software repository
    apt_kanoos='deb http://repo.kano.me/archive/ release main\n'
    apt_file='/etc/apt/sources.list.d/kano.list'
    apt_key_url='http://repo.kano.me/archive/repo.gpg.key'
    apt_key_tmpfile=os.path.join('tmp', os.path.split(apt_key_url)[1])

    # Add KanoOS repository sources to Ubuntu
    Xubuntu.execute('/bin/bash -c "printf \'{}\' > {}"'.format(apt_kanoos, apt_file))
    Xubuntu.execute('wget -O {} {}'.format(apt_key_tmpfile, apt_key_url))
    Xubuntu.execute('apt-key add {}'.format(apt_key_tmpfile))
    Xubuntu.execute('apt-get update')

    # install the extra software - ubuntu desktop, kanoOS software
    if not prepare_only:

        # RaspberryPI Videocore libraries, and wireless dongle firmwares make them available through /opt as in Raspbian
        Xubuntu.execute('apt-get install -y --force-yes libraspberrypi-bin libraspberrypi-dev linux-firmware python-pip --no-install-recommends')

        # This fix is needed to remove the runtime message "error Failed to open vchiq" for GPU-based applications
        fix_videocore_permissions(Xubuntu)

        # Install KanoOS apps straight away
        Xubuntu.execute('apt-get install -y -o Dpkg::Options::="--force-overwrite" --assume-yes {}'.format(kano_packages))

        # Stop the ssh server
        Xubuntu.execute('/etc/init.d/ssh stop')

        # Install KanoOS pip packages
        if len(kano_pip_packages):
            Xubuntu.execute('pip install {}'.format(kano_pip_packages))

        # Fix path to Opengl / Dispmanx libraries
        Xubuntu.execute('ldconfig /opt/vc/lib')

        # unmount the image
        if not Xubuntu.umount():
            print 'WARNING: Image is busy, most likely installation left some running processes, skipping conversion'
            sys.exit(1)

        # Convert the xsysroot image to a raw format ready to flash and boot
        qcow_image=Xubuntu.query('qcow_image')
        print 'Converting image {}...'.format(qcow_image)
        if os.path.isfile(kanubuntu_image):
            os.unlink(kanubuntu_image)

        rc = os.system('qemu-img convert {} {}'.format(qcow_image, kanubuntu_image))

    time_end=time.time()
    print 'Process finished in {} secs - image ready at {}'.format(time_end - time_start, kanubuntu_image)
    sys.exit(0)
