import { useNavigate, useParams } from 'react-router-dom';
import { Button } from '@/components/ui/button';

export default function ProofreadPlaceholder() {
  const { fileId } = useParams();
  const navigate = useNavigate();
  return (
    <div className="space-y-4">
      <Button variant="outline" onClick={() => navigate('/')}>← Back</Button>
      <div className="p-8 border rounded-lg text-center text-muted-foreground">
        <p>
          Proofread editor for file{' '}
          <code className="bg-muted px-1.5 py-0.5 rounded text-foreground">{fileId}</code> coming in A4.
        </p>
        <p className="text-xs mt-2">
          Until then, the legacy{' '}
          <a href="/proofread.html" className="underline">vanilla proofread page</a> still works.
        </p>
      </div>
    </div>
  );
}
