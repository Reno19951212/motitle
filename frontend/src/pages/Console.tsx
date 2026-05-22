import '../styles/motitle-bold.css';
import '../styles/console.css';
import { Rail } from './Console/Rail';
import { QueueColumn } from './Console/QueueColumn';
import { Workbench } from './Console/Workbench';
import { AsideColumn } from './Console/AsideColumn';

export type ConsoleProps = Record<string, never>;

export function Console(_props: ConsoleProps) {
  return (
    <div className="motitle-bold console" data-testid="console-root">
      <div data-testid="console-rail"><Rail /></div>
      <div data-testid="console-queue"><QueueColumn /></div>
      <div data-testid="console-workbench"><Workbench /></div>
      <div data-testid="console-aside"><AsideColumn /></div>
    </div>
  );
}
