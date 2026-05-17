import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { FileCard } from './FileCard';
import type { FileRecord, StageStatus } from '@/lib/socket-events';

const baseFile: FileRecord = {
  id: 'a',
  original_name: 'foo.mp4',
  status: 'completed',
  stage_outputs: [
    { stage_type: 'asr', stage_ref: 'profile-a' },
    { stage_type: 'mt', stage_ref: 'profile-b' },
  ],
};

describe('FileCard', () => {
  it('renders stages with progress', () => {
    render(
      <MemoryRouter>
        <FileCard
          file={baseFile}
          progress={{ 0: 100, 1: 50 }}
          status={{ 0: 'done' as StageStatus, 1: 'running' as StageStatus }}
        />
      </MemoryRouter>
    );
    expect(screen.getByText('foo.mp4')).toBeInTheDocument();
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.getByText('50%')).toBeInTheDocument();
  });

  it('shows Cancel when status=queued + job_id present', () => {
    render(
      <MemoryRouter>
        <FileCard
          file={{ ...baseFile, status: 'queued', job_id: 'j1' }}
          progress={{}}
          status={{}}
        />
      </MemoryRouter>
    );
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });

  it('shows Open when completed', () => {
    render(
      <MemoryRouter>
        <FileCard file={baseFile} progress={{}} status={{}} />
      </MemoryRouter>
    );
    expect(screen.getByRole('button', { name: 'Open' })).toBeInTheDocument();
  });

  it('renders failed badge in destructive variant when status=failed', () => {
    render(
      <MemoryRouter>
        <FileCard
          file={{ ...baseFile, status: 'failed' }}
          progress={{ 0: 30 }}
          status={{ 0: 'failed' as StageStatus }}
        />
      </MemoryRouter>
    );
    expect(screen.getByText('failed')).toBeInTheDocument();
  });
});
