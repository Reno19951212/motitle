import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  RenderOptionsSchema,
  MP4_BITRATE_MODES,
  MP4_PRESETS,
  MP4_PIXEL_FORMATS,
  MP4_PROFILES,
  MP4_LEVELS,
  MP4_AUDIO_BITRATES,
  PRORES_PROFILES,
  PRORES_PROFILE_LABELS,
  AUDIO_BIT_DEPTHS,
  RESOLUTIONS,
  SUBTITLE_SOURCES,
  BILINGUAL_ORDERS,
  type Mp4Options,
  type ProResOptions,
  type XdcamOptions,
  type RenderOptions,
} from '@/lib/schemas/render-options';

type Format = 'mp4' | 'mxf_prores' | 'mxf_xdcam_hd422';

interface Props {
  open: boolean;
  onClose: () => void;
  onConfirm: (options: RenderOptions) => void;
}

const mp4Defaults: Mp4Options = {
  format: 'mp4',
  bitrate_mode: 'crf',
  crf: 18,
  video_bitrate_mbps: 15,
  preset: 'medium',
  pixel_format: 'yuv420p',
  profile: 'high',
  level: 'auto',
  audio_bitrate: '192k',
  resolution: 'keep',
  subtitle_source: 'auto',
  bilingual_order: 'source_top',
};

const proresDefaults: ProResOptions = {
  format: 'mxf_prores',
  prores_profile: '3',
  audio_bit_depth: '24',
  resolution: 'keep',
  subtitle_source: 'auto',
  bilingual_order: 'source_top',
};

const xdcamDefaults: XdcamOptions = {
  format: 'mxf_xdcam_hd422',
  video_bitrate_mbps: 50,
  audio_bit_depth: '24',
  resolution: 'keep',
  subtitle_source: 'auto',
  bilingual_order: 'source_top',
};

interface CommonFieldsValue {
  resolution: (typeof RESOLUTIONS)[number];
  subtitle_source: (typeof SUBTITLE_SOURCES)[number];
  bilingual_order: (typeof BILINGUAL_ORDERS)[number];
}

function CommonFields<T extends CommonFieldsValue>({
  value,
  update,
}: {
  value: T;
  update: <K extends keyof T>(k: K, v: T[K]) => void;
}) {
  return (
    <div className="grid grid-cols-3 gap-3 pt-2 border-t mt-2">
      <div>
        <Label className="text-xs">Resolution</Label>
        <select
          value={value.resolution}
          onChange={(e) => update('resolution' as keyof T, e.target.value as T[keyof T])}
          className="block w-full h-10 rounded-md border border-input bg-background px-2 text-sm"
        >
          {RESOLUTIONS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </div>
      <div>
        <Label className="text-xs">Subtitle source</Label>
        <select
          value={value.subtitle_source}
          onChange={(e) => update('subtitle_source' as keyof T, e.target.value as T[keyof T])}
          className="block w-full h-10 rounded-md border border-input bg-background px-2 text-sm"
        >
          {SUBTITLE_SOURCES.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </div>
      <div>
        <Label className="text-xs">Bilingual order</Label>
        <select
          value={value.bilingual_order}
          onChange={(e) => update('bilingual_order' as keyof T, e.target.value as T[keyof T])}
          className="block w-full h-10 rounded-md border border-input bg-background px-2 text-sm"
        >
          {BILINGUAL_ORDERS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

export function RenderModal({ open, onClose, onConfirm }: Props) {
  const [format, setFormat] = useState<Format>('mp4');
  const [mp4, setMp4] = useState<Mp4Options>(mp4Defaults);
  const [prores, setProres] = useState<ProResOptions>(proresDefaults);
  const [xdcam, setXdcam] = useState<XdcamOptions>(xdcamDefaults);
  const [error, setError] = useState<string | null>(null);

  function patchMp4<K extends keyof Mp4Options>(key: K, value: Mp4Options[K]) {
    setMp4((p) => ({ ...p, [key]: value }));
    setError(null);
  }

  function patchProres<K extends keyof ProResOptions>(key: K, value: ProResOptions[K]) {
    setProres((p) => ({ ...p, [key]: value }));
    setError(null);
  }

  function patchXdcam<K extends keyof XdcamOptions>(key: K, value: XdcamOptions[K]) {
    setXdcam((p) => ({ ...p, [key]: value }));
    setError(null);
  }

  function handleConfirm() {
    setError(null);
    const candidate: RenderOptions =
      format === 'mp4' ? mp4 : format === 'mxf_prores' ? prores : xdcam;
    const parsed = RenderOptionsSchema.safeParse(candidate);
    if (!parsed.success) {
      setError(parsed.error.issues.map((i) => i.message).join('; '));
      return;
    }
    onConfirm(parsed.data);
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Render Output</DialogTitle>
          <DialogDescription>Choose format and encoding options.</DialogDescription>
        </DialogHeader>
        <Tabs value={format} onValueChange={(v) => setFormat(v as Format)}>
          <TabsList>
            <TabsTrigger value="mp4">MP4</TabsTrigger>
            <TabsTrigger value="mxf_prores">MXF ProRes</TabsTrigger>
            <TabsTrigger value="mxf_xdcam_hd422">XDCAM HD 422</TabsTrigger>
          </TabsList>
          <TabsContent value="mp4" className="space-y-3 pt-2">
            <div>
              <Label className="text-xs">Bitrate mode</Label>
              <div className="flex gap-2">
                {MP4_BITRATE_MODES.map((m) => (
                  <Button
                    key={m}
                    size="sm"
                    variant={mp4.bitrate_mode === m ? 'default' : 'outline'}
                    onClick={() => patchMp4('bitrate_mode', m)}
                  >
                    {m.toUpperCase()}
                  </Button>
                ))}
              </div>
            </div>
            {mp4.bitrate_mode === 'crf' && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">CRF (0-51)</Label>
                  <Input
                    type="number"
                    min={0}
                    max={51}
                    value={mp4.crf}
                    onChange={(e) => patchMp4('crf', Number(e.target.value))}
                  />
                </div>
                <div>
                  <Label className="text-xs">Preset</Label>
                  <select
                    value={mp4.preset}
                    onChange={(e) => patchMp4('preset', e.target.value as Mp4Options['preset'])}
                    className="block w-full h-10 rounded-md border border-input bg-background px-2 text-sm"
                  >
                    {MP4_PRESETS.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}
            {(mp4.bitrate_mode === 'cbr' || mp4.bitrate_mode === '2pass') && (
              <div>
                <Label className="text-xs">Video bitrate (Mbps)</Label>
                <Input
                  type="number"
                  min={2}
                  max={100}
                  value={mp4.video_bitrate_mbps}
                  onChange={(e) => patchMp4('video_bitrate_mbps', Number(e.target.value))}
                />
              </div>
            )}
            <div className="grid grid-cols-3 gap-3">
              <div>
                <Label className="text-xs">Pixel format</Label>
                <select
                  value={mp4.pixel_format}
                  onChange={(e) => patchMp4('pixel_format', e.target.value as Mp4Options['pixel_format'])}
                  className="block w-full h-10 rounded-md border border-input bg-background px-2 text-sm"
                >
                  {MP4_PIXEL_FORMATS.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <Label className="text-xs">H.264 Profile</Label>
                <select
                  value={mp4.profile}
                  onChange={(e) => patchMp4('profile', e.target.value as Mp4Options['profile'])}
                  className="block w-full h-10 rounded-md border border-input bg-background px-2 text-sm"
                >
                  {MP4_PROFILES.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <Label className="text-xs">Level</Label>
                <select
                  value={mp4.level}
                  onChange={(e) => patchMp4('level', e.target.value as Mp4Options['level'])}
                  className="block w-full h-10 rounded-md border border-input bg-background px-2 text-sm"
                >
                  {MP4_LEVELS.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <Label className="text-xs">Audio bitrate</Label>
                <select
                  value={mp4.audio_bitrate}
                  onChange={(e) => patchMp4('audio_bitrate', e.target.value as Mp4Options['audio_bitrate'])}
                  className="block w-full h-10 rounded-md border border-input bg-background px-2 text-sm"
                >
                  {MP4_AUDIO_BITRATES.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <CommonFields
              value={mp4}
              update={(k, v) => patchMp4(k as keyof Mp4Options, v as Mp4Options[keyof Mp4Options])}
            />
          </TabsContent>

          <TabsContent value="mxf_prores" className="space-y-3 pt-2">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">ProRes Profile</Label>
                <select
                  value={prores.prores_profile}
                  onChange={(e) => patchProres('prores_profile', e.target.value as ProResOptions['prores_profile'])}
                  className="block w-full h-10 rounded-md border border-input bg-background px-2 text-sm"
                >
                  {PRORES_PROFILES.map((p) => (
                    <option key={p} value={p}>
                      {p} — {PRORES_PROFILE_LABELS[p]}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <Label className="text-xs">Audio bit depth</Label>
                <select
                  value={prores.audio_bit_depth}
                  onChange={(e) => patchProres('audio_bit_depth', e.target.value as ProResOptions['audio_bit_depth'])}
                  className="block w-full h-10 rounded-md border border-input bg-background px-2 text-sm"
                >
                  {AUDIO_BIT_DEPTHS.map((p) => (
                    <option key={p} value={p}>
                      {p}-bit PCM
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <CommonFields
              value={prores}
              update={(k, v) =>
                patchProres(k as keyof ProResOptions, v as ProResOptions[keyof ProResOptions])
              }
            />
          </TabsContent>

          <TabsContent value="mxf_xdcam_hd422" className="space-y-3 pt-2">
            <div>
              <Label className="text-xs">Video bitrate (Mbps): {xdcam.video_bitrate_mbps}</Label>
              <input
                type="range"
                min={10}
                max={100}
                step={5}
                value={xdcam.video_bitrate_mbps}
                onChange={(e) => patchXdcam('video_bitrate_mbps', Number(e.target.value))}
                className="w-full"
                aria-label="XDCAM bitrate"
              />
              <p className="text-xs text-muted-foreground">
                Default 50 Mbps (Sony XDCAM HD 422 broadcast standard)
              </p>
            </div>
            <div>
              <Label className="text-xs">Audio bit depth</Label>
              <select
                value={xdcam.audio_bit_depth}
                onChange={(e) => patchXdcam('audio_bit_depth', e.target.value as XdcamOptions['audio_bit_depth'])}
                className="block w-full h-10 rounded-md border border-input bg-background px-2 text-sm"
              >
                {AUDIO_BIT_DEPTHS.map((p) => (
                  <option key={p} value={p}>
                    {p}-bit PCM
                  </option>
                ))}
              </select>
            </div>
            <CommonFields
              value={xdcam}
              update={(k, v) =>
                patchXdcam(k as keyof XdcamOptions, v as XdcamOptions[keyof XdcamOptions])
              }
            />
          </TabsContent>
        </Tabs>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex justify-end gap-2 pt-3 border-t">
          <Button size="sm" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" onClick={handleConfirm}>
            Confirm
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
