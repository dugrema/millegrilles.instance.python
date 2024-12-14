SET MILLEGRILLES_ROOT=%USERPROFILE%\millegrilles
SET PYTHON_EXE=%MILLEGRILLES_ROOT%\venv\Scripts\python.exe

call %MILLEGRILLES_ROOT%\venv\Scripts\activate.bat
%PYTHON_EXE% --version

cd /d %MILLEGRILLES_ROOT%\git\millegrilles.instance.python

SET WEB_PORT=5443
SET MILLEGRILLES_PATH=%MILLEGRILLES_ROOT%\data
SET MQ_HOSTNAME=localhost
%PYTHON_EXE% -m millegrilles_instance --verbose
