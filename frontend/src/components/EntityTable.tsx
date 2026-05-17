import * as React from 'react';
import { Button } from '@/components/ui/button';
import { Pencil, Trash2 } from 'lucide-react';

export interface Column<T> {
  header: string;
  render: (row: T) => React.ReactNode;
}

export function EntityTable<T extends { id: string }>({
  rows,
  columns,
  onEdit,
  onDelete,
  canEdit,
  canDelete,
}: {
  rows: T[];
  columns: Column<T>[];
  onEdit: (row: T) => void;
  onDelete: (row: T) => void;
  canEdit: (row: T) => boolean;
  canDelete: (row: T) => boolean;
}) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b text-left">
          {columns.map((c) => (
            <th key={c.header} className="p-2 font-medium">{c.header}</th>
          ))}
          <th className="p-2 w-24">Actions</th>
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 && (
          <tr><td colSpan={columns.length + 1} className="p-4 text-center text-muted-foreground">No entries yet.</td></tr>
        )}
        {rows.map((row) => (
          <tr key={row.id} className="border-b hover:bg-muted/30">
            {columns.map((c) => (
              <td key={c.header} className="p-2">{c.render(row)}</td>
            ))}
            <td className="p-2">
              <div className="flex gap-1">
                {canEdit(row) && (
                  <Button size="icon" variant="ghost" onClick={() => onEdit(row)} aria-label="Edit">
                    <Pencil className="h-4 w-4" />
                  </Button>
                )}
                {canDelete(row) && (
                  <Button size="icon" variant="ghost" onClick={() => onDelete(row)} aria-label="Delete">
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                )}
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
