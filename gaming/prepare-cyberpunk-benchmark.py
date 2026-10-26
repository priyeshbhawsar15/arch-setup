#!/usr/bin/env python3
"""Prepare a private, opt-in game-process logger; never launch or reconfigure a game."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import tempfile
import time

MARKER = '# Managed by arch-setups: Cyberpunk benchmark logging'


def profile_text(output):
    output = str(output)
    if not Path(output).is_absolute() or '\n' in output or '\r' in output:
        raise ValueError('Expected a single-line absolute logging path')
    return '\n'.join([
        MARKER, 'no_display', 'fps', 'frametime', 'cpu_stats', 'gpu_stats',
        'gpu_core_clock', 'cpu_mhz', 'ram', 'vram',
        'log_interval=0', 'toggle_logging=Shift_L+F2', 'log_versioning',
        'permit_upload=0', 'upload_logs=0', 'output_folder=' + output, '',
    ])


def prepare(directory=None):
    state = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state'))
    directory = Path(directory) if directory is not None else state / 'arch-setups/benchmarks/cyberpunk'
    if not directory.is_absolute() or directory.is_symlink():
        raise ValueError('Expected an absolute, non-symlink benchmark directory')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    output = directory / 'logs'
    if output.is_symlink():
        raise ValueError('Refusing symlink log directory')
    output.mkdir(exist_ok=True, mode=0o700)
    output.chmod(0o700)
    target = directory / 'MangoHud.conf'
    if target.is_symlink():
        raise ValueError('Refusing symlink benchmark profile')
    text = profile_text(output)
    if target.exists() and not target.read_text().startswith(MARKER + '\n'):
        raise ValueError('Refusing foreign benchmark profile')
    changed = not target.exists() or target.read_text() != text
    if changed:
        if target.exists():
            shutil.copy2(target, target.with_name('MangoHud.conf.backup-' + str(time.time_ns())))
        fd, temporary = tempfile.mkstemp(prefix='.MangoHud-', dir=directory)
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(text)
            os.chmod(temporary, 0o600)
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
    # For the existing HDR helper: enable the Vulkan layer ONLY after Gamescope's
    # child separator. Never inject it into the compositor or nest Gamescope.
    prefix = ('env -u MANGOHUD -u MANGOHUD_CONFIG -u MANGOHUD_CONFIGFILE '
              'steam-gamescope-hdr env MANGOHUD=1 ' + shlex.quote('MANGOHUD_CONFIGFILE=' + str(target)))
    return dict(profile=str(target), logs=str(output), proposed_prefix=prefix, changed=changed,
                activated=False, uploads=False, fps_limit_added=False,
                game_settings_changed=False, logging_toggle='Left Shift + F2')


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(prepare(), indent=2))
