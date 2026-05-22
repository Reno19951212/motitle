import { describe, it, expect, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { PresetPills } from './PresetPills';
import { usePipelinePickerStore, type PipelineSummary } from '../../stores/pipeline-picker';

function makePipeline(id: string, name: string, slot?: 1 | 2 | 3 | 4): PipelineSummary {
  return {
    id, name, description: '', shared: false, user_id: 1,
    preset_slot: slot ?? null,
  };
}

describe('PresetPills', () => {
  it('renders 4 pills with preset_slot mapping', () => {
    usePipelinePickerStore.setState({
      pipelines: [
        makePipeline('p1', '新聞廣播', 1),
        makePipeline('p2', '訪問長片', 2),
        makePipeline('p3', '體育直播', 3),
      ],
      pipelineId: 'p1',
    });
    render(<PresetPills />);
    expect(screen.getByTestId('preset-pill-1').textContent).toContain('新聞廣播');
    expect(screen.getByTestId('preset-pill-2').textContent).toContain('訪問長片');
    expect(screen.getByTestId('preset-pill-3').textContent).toContain('體育直播');
    expect(screen.getByTestId('preset-pill-4').textContent).toContain('未設定');
  });

  it('Cmd+2 switches pipelineId to slot 2 occupant', () => {
    const setPipelineId = vi.fn();
    usePipelinePickerStore.setState({
      pipelines: [makePipeline('p2', 'X', 2)],
      pipelineId: null,
      setPipelineId,
    });
    render(<PresetPills />);
    act(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: '2', metaKey: true }));
    });
    expect(setPipelineId).toHaveBeenCalledWith('p2');
  });
});
