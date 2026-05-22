import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Rail } from './Rail';

describe('Rail', () => {
  it('renders brand mark + 6 nav items + 3 bottom items', () => {
    render(<MemoryRouter><Rail /></MemoryRouter>);
    expect(screen.getByText('M', { selector: '.mark' })).toBeInTheDocument();
    expect(screen.getAllByTestId(/^rail-nav-/)).toHaveLength(6);
    expect(screen.getAllByTestId(/^rail-bottom-/)).toHaveLength(3);
  });

  it('marks the active nav item with .on class', () => {
    render(<MemoryRouter><Rail activeId="files" /></MemoryRouter>);
    const filesItem = screen.getByTestId('rail-nav-files');
    expect(filesItem.className).toMatch(/\bon\b/);
  });
});
