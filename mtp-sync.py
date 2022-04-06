#!/usr/bin/python3
import argparse
import json
import logging
import ntlib.imp as ntimp
import os
import shutil
import time


__author__ = 'NTI (lugino-emeritus) <*@*.de>'
__version__ = '0.1.1'

STATE_FILE = '.mtp_sync_state.json'

parser = argparse.ArgumentParser()
parser.add_argument('src_path', help='source path, no mtp device')
parser.add_argument('dst_path', help='destination path, copied files do not have origin timestamps')
parser.add_argument('-v', '--verbose', action='store_true', help='show debug messages')
parser.add_argument('--safe-mode', action='store_true', help='save new state periodically')
parser.add_argument('--size-only', action='store_true', help='only compare file sizes, no state file')
parser.add_argument('--write-state', action='store_true', help='write state file with --size-only')
opts = parser.parse_args()

ntimp.config_log(logging.DEBUG if opts.verbose else logging.INFO)
_srcpath = os.path.normpath(opts.src_path)
_dstpath = os.path.normpath(opts.dst_path)

#-------------------------------------------------------

def _add_file_stat(path, files, dirs, include):
	logging.debug('recursive scan of %s', path)
	for f in os.scandir(path):
		if f.is_symlink():
			logging.debug('ignore symlink %s', f.path)
			continue
		path = os.path.normpath(f.path)
		if f.is_dir():
			dirs.add(path)
			if include is None or path in include:
				_add_file_stat(f.path, files, dirs, include)
			else:
				logging.debug('ignore folder %s', f.path)
		else:
			stat = f.stat()
			files[path] = (int(stat.st_ctime), stat.st_size)

def get_path_state(path, include=None):
	files = {}
	dirs = set()
	logging.info('scan path %s', path)
	cwd = os.getcwd()
	try:
		os.chdir(path)
		_add_file_stat('.', files, dirs, include)
	finally:
		os.chdir(cwd)
	logging.info('found %d files and %d dirs in %s', len(files), len(dirs), path)
	return {'files': files, 'dirs': dirs}


def sync_dirs(src_dirs, dst_dirs):
	remove = sorted(dst_dirs - src_dirs)
	create = sorted(src_dirs - dst_dirs)
	logging.info('sync dirs: remove %d, create %d', len(remove), len(create))
	for p in remove:
		path = os.path.join(_dstpath, p)
		shutil.rmtree(path)
		logging.debug('removed tree %s', path)
	for p in sorted(create):
		path = os.path.join(_dstpath, p)
		os.mkdir(path)
		logging.debug('created dir %s', path)

#-------------------------------------------------------

class FileState:
	def __init__(self, src_state, dst_state):
		self.src_state = src_state
		self.dst_state = dst_state
		self._compare_states()

	def _compare_states(self):
		src_files = set(self.src_state)
		dst_files = set(self.dst_state)
		self.remove = list(dst_files - src_files)
		self.update = list(src_files - dst_files)
		for p in src_files & dst_files:
			ts_src, size_src = self.src_state[p]
			ts_dst, size_dst = self.dst_state[p]
			if self.src_state[p] != self.dst_state[p]:
				self.update.append(p)

	def info_txt(self):
		return f'sync files: remove {len(self.remove)}, update {len(self.update)}'

	def rm(self, p):
		path = os.path.join(_dstpath, p)
		os.remove(path)
		del self.dst_state[p]
		logging.debug('removed file %s', path)

	def cp(self, p):
		shutil.copyfile(os.path.join(_srcpath, p), os.path.join(_dstpath, p))
		self.dst_state[p] = self.src_state[p]
		logging.debug('copied file %s', p)


def read_mtp_state():
	state_path = os.path.join(_dstpath, STATE_FILE)
	try:
		with open(state_path, 'r') as f:
			state = json.load(f)
			logging.info('mtp_state %s loaded', state_path)
			return state
	except FileNotFoundError:
		if input(f'State file ({state_path}) not found. Continue (y|N)? ').lower() == 'y':
			return {}
		raise FileNotFoundError(f'no mtp_state file: {state_path}') from None

def update_states(src_state, dst_state, mtp_state=None):
	if STATE_FILE in src_state:
		del src_state[STATE_FILE]
		logging.warning('ignore src state file (%s)', os.path.join(_srcpath, STATE_FILE))
	if STATE_FILE in dst_state:
		del dst_state[STATE_FILE]
	elif mtp_state is not None:
		logging.warning('missing dst state file (%s)', os.path.join(_dstpath, STATE_FILE))

	if mtp_state:
		def get_ts(p):
			ts = mtp_state.get(p, -1)
			if ts == -1:
				logging.warning('path %s missing in mtp_state', p)
			return ts
	elif mtp_state is None:
		get_ts = lambda p: src_state.get(p, (-1, 0))[0]
	else:
		get_ts = lambda p: -1
	for p, (_, size) in dst_state.items():
		dst_state[p] = (get_ts(p), size)

def write_mtp_state(dst_state):
	state_path = os.path.join(_dstpath, STATE_FILE)
	mtp_state = {p: ts for p, (ts, _) in dst_state.items()}
	with open(state_path, 'w') as f:
		logging.info('update mtp_state %s', state_path)
		json.dump(mtp_state, f, separators=(',\n', ':'))

def time_mtp_state(dst_state):
	t0 = time.monotonic()
	write_mtp_state(dst_state)
	return time.monotonic() - t0

#-------------------------------------------------------

def print_caption(s):
	print(f"-----{s.join((' ', ' ')):-<50s}")

ts_start = time.time()
print_caption('START SYNC')
src_pstate = get_path_state(_srcpath)
dst_pstate = get_path_state(_dstpath, include=src_pstate['dirs'])
# scan destination before loading state file reduces time of read_mtp_state
mtp_state = None if opts.size_only else read_mtp_state()
update_states(src_pstate['files'], dst_pstate['files'], mtp_state)
fs = FileState(src_pstate['files'], dst_pstate['files'])

try:
	sync_dirs(src_pstate['dirs'], dst_pstate['dirs'])
	logging.info(fs.info_txt())
	for p in fs.remove:
		fs.rm(p)
	if not opts.safe_mode:
		for p in fs.update:
			fs.cp(p)
	else:
		delay = 30
		next_save = time.monotonic() + delay
		for p in fs.update:
			if time.monotonic() > next_save:
				t0 = time.monotonic()
				write_mtp_state(dst_pstate['files'])
				dt = time.monotonic() - t0
				logging.debug('write_mtp_state takes %.2fs', dt)
				delay += dt - delay/4  # delay converges to 4 * dt
				if delay < 30:
					delay = 30
				elif delay > 120:
					logging.warning('saving mtp state is slow (%.2fs), set delay to 120s', dt)
					delay = 120
				next_save = time.monotonic() + delay
			fs.cp(p)

except KeyboardInterrupt:
	logging.warning('synchronization stopped by user')
finally:
	if not opts.size_only or opts.write_state:
		write_mtp_state(dst_pstate['files'])
	print_caption(f'DONE IN {(time.time()-ts_start):.2f}s')
