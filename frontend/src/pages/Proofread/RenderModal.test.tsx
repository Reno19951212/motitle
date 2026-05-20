import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { RenderModal } from './RenderModal';

const baseProps = {
  availableLangs: ['zh', 'en'],
  defaultLang: 'zh',
};

describe('RenderModal', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <RenderModal open={false} onClose={vi.fn()} onConfirm={vi.fn()} {...baseProps} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('shows MP4 form by default + confirm with default options + targetLang', () => {
    const onConfirm = vi.fn();
    render(<RenderModal open onClose={vi.fn()} onConfirm={onConfirm} {...baseProps} />);
    expect(screen.getByText('Render Output')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    expect(onConfirm).toHaveBeenCalledWith(
      expect.objectContaining({ format: 'mp4', bitrate_mode: 'crf' }),
      'zh',
    );
  });

  it('shows error on cross-field validation failure', () => {
    render(<RenderModal open onClose={vi.fn()} onConfirm={vi.fn()} {...baseProps} />);
    // Change pixel_format to yuv422p (which requires high422), but keep profile=high
    const pixelSelect = screen.getByDisplayValue('yuv420p') as HTMLSelectElement;
    fireEvent.change(pixelSelect, { target: { value: 'yuv422p' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    expect(screen.getByText(/pixel_format and H\.264 profile must match/)).toBeInTheDocument();
  });

  it('switches to MXF ProRes tab + confirms with default options', () => {
    const onConfirm = vi.fn();
    render(<RenderModal open onClose={vi.fn()} onConfirm={onConfirm} {...baseProps} />);
    const proresTab = screen.getByRole('tab', { name: 'MXF ProRes' });
    fireEvent.mouseDown(proresTab);
    fireEvent.click(proresTab);
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    expect(onConfirm).toHaveBeenCalledWith(
      expect.objectContaining({ format: 'mxf_prores', prores_profile: '3' }),
      'zh',
    );
  });

  it('switches to XDCAM HD 422 tab + confirms with default options', () => {
    const onConfirm = vi.fn();
    render(<RenderModal open onClose={vi.fn()} onConfirm={onConfirm} {...baseProps} />);
    const xdcamTab = screen.getByRole('tab', { name: 'XDCAM HD 422' });
    fireEvent.mouseDown(xdcamTab);
    fireEvent.click(xdcamTab);
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    expect(onConfirm).toHaveBeenCalledWith(
      expect.objectContaining({ format: 'mxf_xdcam_hd422', video_bitrate_mbps: 50 }),
      'zh',
    );
  });

  it('target-lang picker emits selected lang on confirm', () => {
    const onConfirm = vi.fn();
    render(
      <RenderModal
        open
        onClose={vi.fn()}
        onConfirm={onConfirm}
        availableLangs={['zh', 'en']}
        defaultLang="zh"
      />,
    );
    const langSelect = screen.getByLabelText(/Target Language/) as HTMLSelectElement;
    fireEvent.change(langSelect, { target: { value: 'en' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    expect(onConfirm).toHaveBeenCalledWith(expect.anything(), 'en');
  });
});
