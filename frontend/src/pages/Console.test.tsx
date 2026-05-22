import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Console } from './Console';

function renderConsole() {
  return render(
    <MemoryRouter initialEntries={['/console?console=1']}>
      <Console />
    </MemoryRouter>,
  );
}

describe('Console page', () => {
  it('renders 4 main columns', () => {
    renderConsole();
    expect(screen.getByTestId('console-rail')).toBeInTheDocument();
    expect(screen.getByTestId('console-queue')).toBeInTheDocument();
    expect(screen.getByTestId('console-workbench')).toBeInTheDocument();
    expect(screen.getByTestId('console-aside')).toBeInTheDocument();
  });
});
