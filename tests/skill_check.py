import tempfile,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
validator=Path('/home/vermeille/.codex/skills/.system/skill-creator/scripts/quick_validate.py')
for source in (root/'skills').glob('*.md'):
 with tempfile.TemporaryDirectory() as d:
  p=Path(d)/('table-'+source.stem);p.mkdir();(p/'SKILL.md').write_text(source.read_text())
  subprocess.run([sys.executable,str(validator),str(p)],check=True)
