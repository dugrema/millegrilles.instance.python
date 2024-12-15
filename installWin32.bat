REM Copier les fichiers vers user data
SET MILLEGRILLES_ROOT=%USERPROFILE%\AppData\Local\millegrilles
SET PYTHON_VENV=%MILLEGRILLES_ROOT%\venv

echo Creer %MILLEGRILLES_ROOT%
mkdir %MILLEGRILLES_ROOT%
mkdir %MILLEGRILLES_ROOT%\data
mkdir %MILLEGRILLES_ROOT%\data\configuration
mkdir %MILLEGRILLES_ROOT%\data\configuration\catalogues
mkdir %MILLEGRILLES_ROOT%\python

echo Copier fichiers de configuration
copy .\etc\catalogues\signed\*.* %MILLEGRILLES_ROOT%\data\configuration\catalogues\
copy .\etc\idmg_validation.json %MILLEGRILLES_ROOT%\data\configuration\
xcopy /y .\etc\docker\ %MILLEGRILLES_ROOT%\data\configuration\docker\
xcopy /y /s .\etc\nginx\ %MILLEGRILLES_ROOT%\data\configuration\nginx\
xcopy /y .\etc\webappconfig\ %MILLEGRILLES_ROOT%\data\configuration\webappconfig\
xcopy /y /s .\millegrilles_instance\ %MILLEGRILLES_ROOT%\python\millegrilles_instance\
copy bin\startMillegrilles.bat %MILLEGRILLES_ROOT%\

echo Creer environnement virtuel python
%USERPROFILE%\AppData\Local\Programs\Python\Launcher\py -m venv %MILLEGRILLES_ROOT%\venv

echo Installer dependances python
call %PYTHON_VENV%\Scripts\activate.bat
%PYTHON_VENV%\Scripts\pip.exe install -r requirements.txt

echo Pret a demarrer. 
echo Utilisez le script %MILLEGRILLES_ROOT%\startMillegrilles.bat pour demarrer l'agent d'instance.
