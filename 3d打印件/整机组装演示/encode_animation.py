"""Encode the verified Blender frames with Chinese step captions."""
from pathlib import Path
import subprocess
import shutil
import json

out=Path(__file__).resolve().parent
frames=[out/'frames'/f'frame_{i:04d}.png' for i in range(1,577)]
assert all(p.is_file() for p in frames), 'Render all 576 frames before encoding'
ffmpeg=shutil.which('ffmpeg')
ffprobe=shutil.which('ffprobe')
assert ffmpeg and ffprobe, 'FFmpeg and FFprobe are required'
cmd=[ffmpeg,'-hide_banner','-loglevel','warning','-y','-framerate','24','-start_number','1',
     '-i','frames/frame_%04d.png','-frames:v','576','-vf',
     'pad=1280:920:0:84:color=0xf8f5eb,subtitles=assembly_captions.ass',
     '-c:v','libx264','-preset','medium','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',
     'assembly_animation.mp4']
subprocess.run(cmd,cwd=out,check=True)
result=subprocess.run([ffprobe,'-v','error','-select_streams','v:0','-count_frames',
    '-show_entries','stream=codec_name,width,height,r_frame_rate,nb_read_frames,duration',
    '-of','json','assembly_animation.mp4'],cwd=out,check=True,capture_output=True,text=True)
probe=json.loads(result.stdout)
v=probe['streams'][0]
assert v['nb_read_frames']=='576' and float(v['duration'])==24
assert v['codec_name']=='h264' and v['r_frame_rate']=='24/1'
report={'video':probe,'all_576_source_frames_present':True,
        'dimensions':[1280,920],'caption_file':'assembly_captions.ass','audio':'none',
        'rendering':'Blender Workbench animation / Eevee still images'}
(out/'media_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
