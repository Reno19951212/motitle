import { Button } from '@/components/ui/button';

export function App() {
  return (
    <div className="p-8 space-y-4">
      <h1 className="text-2xl font-semibold">MoTitle — A3 bootstrap</h1>
      <p className="text-muted-foreground">Frontend foundation under construction.</p>
      <div className="flex gap-2">
        <Button>Primary</Button>
        <Button variant="outline">Outline</Button>
        <Button variant="destructive">Destructive</Button>
        <Button variant="ghost">Ghost</Button>
      </div>
    </div>
  );
}
