import numpy as np
import torch


from tqdm import tqdm
from logger.utils import DotDict
import multiprocessing
import soundfile as sf
import click
from pathlib import Path
from preprocess import Preprocessor
from ddsp.vocoder import load_model

def infer(
        model : torch.nn.Module, 
        input : Path, 
        output: Path, 
        args  : DotDict, 
        key   : float, 
        device: str, 
        sample_rate: int
):
    '''
    Args:
        input : audio file path
        output: output audio file path
        key   : the key change in semitones   
    '''
    # Process single file
    print(f"Processing file: {input}")
    audio, sr = sf.read(str(input))

    assert sr == sample_rate, f"\
                            Sample rate of input file {sr} does not match \
                            model sample rate {sample_rate}"
    
    # preprocess
    preprocessor = Preprocessor(args, device)
    mel, f0, uv=preprocessor.mel_f0_uv_process(torch.from_numpy(audio).float())

    print(f"Input shape: {mel.shape}, F0 shape: {f0.shape}, UV shape: {uv.shape}")
    print("f0dtype: ", f0.dtype, "uvdtype: ", uv.dtype)
    mel = mel.astype(np.float32)
    f0 = f0.astype(np.float32)
    uv = uv.astype(np.float32)
    print("f0dtype: ", f0.dtype, "uvdtype: ", uv.dtype)
   # np.save(output.with_suffix('.npy'), mel)
    
    
    # key change
    key_change = float(key)
    if key_change != 0:
        output_f0 = f0 * 2 ** (key_change / 12)
    else:
        output_f0 = None

    # forward and save the output
    with torch.no_grad():
        if output_f0 is None:
            signal, _, (s_h, s_n), (sin_mag, sin_phase) = model(torch.tensor(mel).float().unsqueeze(0).to(device), torch.tensor(f0).unsqueeze(0).unsqueeze(-1).to(device))
        else:
            signal, _, (s_h, s_n) = model(torch.tensor(mel).float().unsqueeze(0).to(device), torch.tensor(f0).unsqueeze(0).unsqueeze(-1).to(device))
        signal = signal.squeeze().cpu().numpy()
        s_h = s_h.squeeze().cpu().numpy()
        s_n = s_n.squeeze().cpu().numpy()
        sf.write(str(output), signal, args.data.sampling_rate,subtype='FLOAT') 
        sf.write(str(output.with_suffix('.harmonic.wav')), s_h, args.data.sampling_rate,subtype='FLOAT') 
        sf.write(str(output.with_suffix('.noise.wav')), s_n, args.data.sampling_rate,subtype='FLOAT') 

@click.command()
@click.option(
    '--model_path', type=click.Path(
        exists=True, file_okay=True, dir_okay=False, readable=True,
        path_type=Path, resolve_path=True
    ),
    required=True, metavar='CONFIG_FILE',
    help='The path to the model.'
)
@click.option(
    '--input', type=click.Path(
        exists=True, file_okay=True, dir_okay=True, readable=True,
        path_type=Path, resolve_path=True
    ),
    required=True, 
    help='The path to the WAV file or directory containing WAV files.'
)
@click.option(
    '--output', type=click.Path(
        exists=True, file_okay=True, dir_okay=True, readable=True,
        path_type=Path, resolve_path=True
    ),
    required=True, 
    help='The path to the output directory.'
)
@click.option(
    '--key', type=int, default=0,
    help='key changed (number of semitones)'
)

def main(model_path, input, output, key):

    # cpu inference is fast enough!
    device = 'cpu' 
    #device = 'cuda' if torch.cuda.is_available() else 'cpu'

    model, args = load_model(model_path, device=device)
    print(f"Model loaded: {model_path}")

    if input.is_file():
        infer(model, input, output / input.name, args, key, device, args.data.sampling_rate)
    elif input.is_dir():
        assert output.is_dir(),\
              "If input is a directory, output must be a directory as well."
        for file in tqdm(input.glob('*.wav')):
            infer(  
                model,  
                file,  
                output / file.name,  
                args,  
                key,  
                device,  
                args.data.sampling_rate  
            )
if __name__ == '__main__':
    main()