import os, subprocess, tarfile, tempfile, unittest
from pathlib import Path
SCRIPT=Path(__file__).resolve().parents[1]/'deploy/backup.sh'
class BackupTests(unittest.TestCase):
 def run_backup(self, running='true', fail_stop=False):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
  for name in ['deploy/data','deploy/patches','deploy/telegram','plugin','bin']:(root/name).mkdir(parents=True)
  for name in ['deploy/compose.yaml','deploy/Dockerfile','deploy/data/memory.db']:(root/name).write_text('fixture')
  docker=root/'bin/docker'
  docker.write_text('#!/bin/sh\necho "$*" >> "$TEST_ROOT/calls"\nif [ "$1" = inspect ]; then echo "$TEST_RUNNING"; fi\ncase "$*" in *"stop astrbot"*) if [ "$TEST_FAIL_STOP" = 1 ]; then exit 1; fi;; esac\n')
  docker.chmod(0o755)
  env={**os.environ,'PATH':str(root/'bin')+':'+os.environ['PATH'],'TEST_ROOT':str(root),'TEST_RUNNING':running,'TEST_FAIL_STOP':str(int(fail_stop))}
  result=subprocess.run(['bash',str(SCRIPT),str(root)],env=env,capture_output=True,text=True)
  return root,result
 def test_running_service_restored_and_paths_recoverable(self):
  root,result=self.run_backup();self.assertEqual(result.returncode,0,result.stderr)
  self.assertIn('start astrbot',(root/'calls').read_text())
  with tarfile.open(next((root/'backups').glob('*.tar.gz'))) as archive:
   self.assertIn('deploy/data/memory.db',archive.getnames())
   self.assertTrue(all(not name.startswith(('../','/')) for name in archive.getnames()))
 def test_stopped_service_stays_stopped(self):
  root,result=self.run_backup('false');self.assertEqual(result.returncode,0,result.stderr)
  self.assertNotIn('start astrbot',(root/'calls').read_text())
 def test_failed_stop_aborts_before_archive(self):
  root,result=self.run_backup(fail_stop=True);self.assertNotEqual(result.returncode,0)
  self.assertFalse(list((root/'backups').glob('*.tar.gz')))
if __name__=='__main__':unittest.main()
