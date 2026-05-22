import { describe, it, expect } from 'vitest';
import { toConsoleFile } from './to-console-file';
import type { FileRecord } from '../../lib/socket-events';

describe('toConsoleFile', () => {
  const baseFile: FileRecord = {
    id: 'f1',
    original_name: 'Bulletin.mp4',
    status: 'transcribing',
    duration_seconds: 862,        // 14:22
    size: 284 * 1024 * 1024,
    uploaded_at: 1716000000,
    segment_count: 100,
    approved_count: 30,
    stage_outputs: [{ stage_type: 'asr', stage_ref: 'whisper' }],
  };

  it('normalizes FileRecord into ConsoleFile shape', () => {
    const cf = toConsoleFile(baseFile, {}, { nowSeconds: 1716000060 });
    expect(cf.id).toBe('f1');
    expect(cf.name).toBe('Bulletin.mp4');
    expect(cf.ext).toBe('MP4');
    expect(cf.durationSeconds).toBe(862);
    expect(cf.formattedDuration).toBe('14:22');
    expect(cf.formattedSize).toBe('284.0 MB');
    expect(cf.formattedUploaded).toBe('1 分鐘前');
    expect(cf.errored).toBe(false);
  });

  it('handles null duration', () => {
    const cf = toConsoleFile({ ...baseFile, duration_seconds: null }, {}, { nowSeconds: 1716000060 });
    expect(cf.formattedDuration).toBe('—');
  });

  it('marks errored when status === failed', () => {
    const cf = toConsoleFile({ ...baseFile, status: 'failed' }, {}, { nowSeconds: 1716000060 });
    expect(cf.errored).toBe(true);
  });

  it('uppercase extension extraction', () => {
    const cf = toConsoleFile({ ...baseFile, original_name: 'foo.MoV' }, {}, { nowSeconds: 1716000060 });
    expect(cf.ext).toBe('MOV');
  });
});
