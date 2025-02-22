# Common bootstrap functionality.

from __future__ import print_function
import glob, os, platform, re, shutil, sys
import tarfile, tempfile, uuid, zipfile
from contextlib import closing
from subprocess import check_call, call

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from download import Downloader

windows = platform.system() == 'Windows'
opt_dir = r'\Program Files' if windows else '/opt'

# Downloads to a temporary file in the current directory.
# When running in a Vagrant VM, the current directory is in a synced folder so
# this reduces VM growth.
def download(url, cookie=None):
  return Downloader('.').download(url, cookie);

# If we are in a VM managed by Vagrant, then do everything in the shared
# /vagrant directory to avoid growth of the VM drive.
vagrant_dir = '/vagrant'
def bootstrap_init():
  if os.path.exists(vagrant_dir):
    os.chdir(vagrant_dir)
    return True
  return False

# Returns executable location.
def which(name):
  filename = name + '.exe' if windows else name
  for path in os.environ['PATH'].split(os.pathsep):
    path = os.path.join(path.strip('"'), filename)
    if os.path.isfile(path) and os.access(path, os.X_OK):
      return path
  return None

# Returns true if executable is installed on the path.
def installed(name):
  path = which(name)
  if path:
    print(name, 'is installed in', path)
  return path != None

def create_symlink(filename, linkname):
  if not os.path.exists(linkname):
    print('Creating a symlink from', linkname, 'to', filename)
    os.symlink(filename, linkname)
  else:
    print('File already exists:', linkname)

# Adds path to search paths.
def add_to_path(path, linkname=None, isdir=False):
  paths = os.environ['PATH'].split(os.pathsep)
  dir = path if isdir else os.path.dirname(path)
  print('Adding', dir, 'to PATH')
  if isdir:
    paths.insert(0, dir)
  else:
    paths.append(dir)
  os.environ['PATH'] = os.pathsep.join(paths)
  if windows:
    check_call(['setx', '/m', 'PATH', os.environ['PATH']])
  if windows or isdir:
    return
  dir = '/usr/local/bin'
  # Create /usr/local/bin directory if it doesn't exist which can happen
  # on OS X.
  if not os.path.exists(dir):
    os.makedirs(dir)
  linkname = os.path.join(dir, linkname or os.path.basename(path))
  create_symlink(path, linkname)

# Downloads and installs CMake.
# package: The name of a CMake package,
# e.g. 'cmake-2.8.12.2-Linux-i386.tar.gz'.
def install_cmake(package, **kwargs):
  if kwargs.get('check_installed', True) and installed('cmake'):
    return
  dir, version, minor = re.match(
    r'(cmake-(\d+\.\d+)\.(\d+).*-[^\.]+)\..*', package).groups()
  # extractall overwrites existing files, so no need to prepare the
  # destination.
  url = 'https://cmake.org/files/v{0}/{1}'.format(version, package)
  install_dir = kwargs.get('install_dir', opt_dir)
  with Downloader(kwargs.get('download_dir', '.')).download(url) as f:
    iszip = package.endswith('zip')
    with zipfile.ZipFile(f) if iszip \
         else closing(tarfile.open(f, 'r:gz')) as archive:
      archive.extractall(install_dir)
  dir = os.path.join(install_dir, dir)
  if platform.system() == 'Darwin':
    dir = glob.glob(os.path.join(dir, 'CMake*.app', 'Contents'))[0]
  cmake_path = os.path.join(dir, 'bin', 'cmake')
  if install_dir != '.':
    add_to_path(cmake_path)
  return cmake_path

# Downloads and installs Maven.
def install_maven(**kwargs):
  if installed('mvn'):
    return
  # 3.2.5 is the most recent version of Maven compatible with Java 6.
  dir = 'apache-maven-3.2.5'
  url = 'http://mirrors.sonic.net/apache/maven/maven-3/3.2.5/binaries/{0}-bin.tar.gz'.format(dir)
  install_dir = kwargs.get('install_dir', opt_dir)
  with Downloader(kwargs.get('download_dir', '.')).download(url) as f:
    with closing(tarfile.open(f, 'r:gz')) as archive:
      archive.extractall(install_dir)
  add_to_path(os.path.join(install_dir, dir, 'bin', 'mvn'))

# Install f90cache.
def install_f90cache():
  if not installed('f90cache'):
    f90cache = 'f90cache-0.96'
    tempdir = tempfile.mkdtemp(suffix='f90cache', dir='')
    with download(
        'http://people.irisa.fr/Edouard.Canot/f90cache/' +
        f90cache + '.tar.bz2', False) as f:
      with closing(tarfile.open(f, "r:bz2")) as archive:
        archive.extractall(tempdir)
    f90cache_dir = os.path.join(tempdir, f90cache)
    check_call(['sh', 'configure'], cwd=f90cache_dir)
    check_call(['make', 'all', 'install'], cwd=f90cache_dir)
    shutil.rmtree(tempdir)

# Returns true iff module exists.
def module_exists(module):
  try:
    __import__(module)
    return True
  except ImportError:
    return False

# Install package using pip if it hasn't been installed already.
def pip_install(package, test_module=None):
  if not test_module:
    test_module = package.split('==')[0]
  if module_exists(test_module):
    return
  # If pip doesn't exist install it first.
  if not module_exists('pip'):
    with download('https://bootstrap.pypa.io/get-pip.py') as f:
      check_call(['python', f])
  # Install pip 6.1.1 because buildbot-slave installation is broken in pip 7.0.0:
  # https://github.com/pypa/pip/issues/2996
  # Also run pip via Python, not using script, because the latter fails on Windows
  # due to file locking.
  # check_call(['python', '-m', 'pip.__main__', 'install', 'pip==6.1.1'])
  # Install the package.
  print('Installing', package)
  check_call(['pip', 'install', package])

# Installs buildbot slave.
def install_buildbot_slave(name, path=None, script_dir='', shell=False, **args):
  username = 'vagrant'
  if platform.system() == 'Linux':
    # Create buildbot user if it doesn't exist.
    username = 'buildbot'
    import pwd
    try:
      pwd.getpwnam(username)
    except KeyError:
      check_call(['sudo', 'useradd', '--system', '--home', '/var/lib/buildbot',
                  '--create-home', '--shell', '/bin/false', 'buildbot'])
  path = path or os.path.expanduser('~{0}/slave'.format(username))
  if os.path.exists(path):
    return None
  # Install twisted 15.4.0 because newer version require Python 2.7 unavailable
  # on Ubuntu 10.04.
  pip_install('twisted==15.4.0')
  pip_install('buildbot-slave', 'buildbot')
  # The password is insecure but it doesn't matter as the buildslaves are
  # not publicly accessible.
  command = [os.path.join(script_dir, 'buildslave'),
             'create-slave', path, args.get('ip', '10.0.2.2'), name, 'pass']
  if not windows:
    command = ['sudo', '-u', username] + command
  check_call(command, shell=shell)
  return path

# Copies optional dependencies from <source_dir>/opt/<platform> to /opt.
def copy_optional_dependencies(platform, source_dir=''):
  source_path = os.path.join(source_dir, 'opt')
  if os.path.exists(source_path):
    for src in glob.glob(os.path.join(source_path, platform, '*')):
      dest = '/opt/' + os.path.basename(src)
      if not os.path.exists(dest):
        print('Copying {0} to {1}'.format(src, dest))
        shutil.copytree(src, dest, symlinks=True)

# Installs an OS X package.
def install_pkg(filename, allow_untrusted=False):
  print('Installing', filename)
  cmd = ['sudo', 'installer', '-pkg', filename, '-target', '/']
  if allow_untrusted:
    cmd.append('-allowUntrusted')
  check_call(cmd)

# Installs a package from a .dmg file.
def install_dmg(filename, allow_untrusted=False):
  dir = tempfile.mkdtemp()
  check_call(['hdiutil', 'attach', filename, '-mountpoint', dir])
  install_pkg(glob.glob(dir + '/*pkg')[0], allow_untrusted)
  check_call(['hdiutil', 'detach', dir])
  os.rmdir(dir)

LOCALSOLVER_VERSION = '5_5_20151124'
LOCALSOLVER_DOWNLOADS_URL = \
  'http://www.localsolver.com/downloads/archives/' + LOCALSOLVER_VERSION + '/'

jdk_update = 79
jdk_download_url = 'http://download.oracle.com/otn-pub/java/jdk/7u{0}-b15/'.format(jdk_update)
jdk_cookie = 'oraclelicense=accept-securebackup-cookie'
