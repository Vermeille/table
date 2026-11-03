"""Initialize only Table's private volume for the configured Hermes runtime UID."""
import os,sys
from pathlib import Path
uid,gid=map(int,sys.argv[1].split(':'))
if uid<=0 or gid<=0:raise SystemExit('Table must run as a non-root user.')
root=Path('/table-data')
# Keep the volume nonempty: Docker otherwise reapplies image directory ownership
# on the next mount, undoing a custom UID initialization.
fd=os.open(root/'.table-volume-initialized',os.O_CREAT|os.O_WRONLY|os.O_NOFOLLOW,0o600);os.close(fd)
os.chown(root,uid,gid);root.chmod(0o700)
for directory,dirs,files in os.walk(root,followlinks=False):
    for name in dirs+files:os.chown(Path(directory)/name,uid,gid,follow_symlinks=False)
print('Table volume initialized for the configured non-root runtime user.')
