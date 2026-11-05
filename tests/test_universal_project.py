import tempfile, unittest, shutil
from pathlib import Path
from src.project_builder import build_project
from src.runner import run_compiled_program
from analyzers.correctness import evaluate_correctness

class UniversalProjectTests(unittest.TestCase):
    def test_auto_builds_nested_multifile_c_project(self):
        if not shutil.which('gcc'): self.skipTest('gcc unavailable')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); project=root/'project'; (project/'src').mkdir(parents=True)
            (project/'src'/'helper.c').write_text('int twice(int x){return 2*x;}')
            (project/'src'/'main.c').write_text('#include <stdio.h>\nint twice(int); int main(void){printf("%d\\n",twice(4));return 0;}')
            result=build_project(project,root/'build',{'build_system':'auto'})
            self.assertEqual(result['status'],'ok',result)
            run=run_compiled_program(result['executable_path'],timeout=2)
            self.assertEqual(run['stdout'].strip(),'8')
    def test_custom_build_rejects_shell_or_unlisted_tool(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/'main.c').write_text('int main(void){return 0;}')
            result=build_project(root,root/'build',{'build_system':'custom','steps':[['bash','-c','echo unsafe']]})
            self.assertEqual(result['error'],'disallowed_build_tool')
    def test_correctness_supports_argv_and_input_output_files(self):
        if not shutil.which('gcc'): self.skipTest('gcc unavailable')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); source=root/'main.c'; exe=root/'prog'
            source.write_text('#include <stdio.h>\nint main(int argc,char**argv){FILE*f=fopen("in.txt","r");int x=0;if(f){fscanf(f,"%d",&x);fclose(f);}FILE*g=fopen("out.txt","w");if(g){fprintf(g,"%d",x+argc);fclose(g);}printf("%s\\n",argv[1]);return 0;}')
            import subprocess
            subprocess.run(['gcc',str(source),'-o',str(exe)],check=True)
            cases=[{'name':'argv_and_files','input':'','args':['hello'],'files':{'in.txt':'5'},'expected_output':'hello','expected_files':{'out.txt':'7'}}]
            result=evaluate_correctness(str(exe),cases)
            self.assertEqual(result.score,100,result.feedback)
    def test_file_output_mismatch_fails(self):
        if not shutil.which('gcc'): self.skipTest('gcc unavailable')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); source=root/'main.c'; exe=root/'prog'
            source.write_text('#include <stdio.h>\nint main(void){FILE*f=fopen("out.txt","w");fputs("wrong",f);fclose(f);return 0;}')
            import subprocess
            subprocess.run(['gcc',str(source),'-o',str(exe)],check=True)
            result=evaluate_correctness(str(exe),[{'files':{},'expected_output':'','expected_files':{'out.txt':'right'}}])
            self.assertEqual(result.score,0)

if __name__=='__main__': unittest.main()
