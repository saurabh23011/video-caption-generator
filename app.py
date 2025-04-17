import streamlit as st
import os
import tempfile
import shutil
import whisper
import srt
from datetime import timedelta
import subprocess
import openai

# Set page configuration
st.set_page_config(
    page_title="Caption Generator",
    page_icon="🎬",
    layout="wide"
)

# Create directory structure if it doesn't exist
for directory in ["uploads", "audio", "videos", "captions"]:
    os.makedirs(directory, exist_ok=True)

# Function to transcribe audio using Whisper
def transcribe_audio(audio_path):
    model = whisper.load_model("base")
    result = model.transcribe(audio_path)
    return result

# Function to convert transcription to SRT format
def convert_to_srt(transcription_result):
    segments = transcription_result['segments']
    subtitles = []
    for i, seg in enumerate(segments):
        subtitle = srt.Subtitle(index=i+1,
                              start=timedelta(seconds=seg['start']),
                              end=timedelta(seconds=seg['end']),
                              content=seg['text'].strip())
        subtitles.append(subtitle)
    return srt.compose(subtitles)

# Function to translate text using OpenAI
def translate_text_openai(text, api_key, target_language="Spanish"):
    openai.api_key = api_key
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": f"You are a translation engine that translates text into {target_language}."},
                {"role": "user", "content": f"Translate the following text to {target_language}: {text}"}
            ],
            temperature=0
        )
        translation = response.choices[0].message.content.strip()
        return translation
    except Exception as e:
        st.error(f"Translation error: {e}")
        return text

# Function to translate SRT content
def translate_srt_openai(srt_content, api_key, target_language="Spanish"):
    subtitles = list(srt.parse(srt_content))
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, subtitle in enumerate(subtitles):
        status_text.text(f"Translating subtitle {i+1}/{len(subtitles)}...")
        translated_text = translate_text_openai(subtitle.content, api_key, target_language)
        subtitle.content = translated_text
        progress_bar.progress((i+1)/len(subtitles))
    
    status_text.text("Translation completed!")
    return srt.compose(subtitles)

# Function to convert SRT to WebVTT
def srt_to_webvtt(srt_content):
    subtitles = list(srt.parse(srt_content))
    srt_formatted = srt.compose(subtitles)
    webvtt_content = "WEBVTT\n\n" + srt_formatted.replace(",", ".")
    return webvtt_content

# Function to extract audio from video
def extract_audio(video_path, audio_path):
    try:
        command = f'ffmpeg -i "{video_path}" -q:a 0 -map a "{audio_path}" -y'
        subprocess.run(command, shell=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        st.error(f"Error extracting audio: {e}")
        return False

# Function to burn subtitles into video
def burn_subtitles(video_path, srt_path, output_path):
    try:
        command = f'ffmpeg -i "{video_path}" -vf "subtitles={srt_path}" "{output_path}"'
        subprocess.run(command, shell=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        st.error(f"Error burning subtitles: {e}")
        return False

# Main application
def main():
    st.title("🎬 Video Caption Generator")
    st.subheader("Transcribe, Translate, and Add Captions to Videos")
    
    # Create tabs for different functionalities
    tab1, tab2, tab3 = st.tabs(["Upload & Process", "View Results", "Settings"])
    
    with tab1:
        st.header("Upload and Process Video")
        
        # File uploader
        uploaded_file = st.file_uploader("Choose a video file", type=["mp4", "mov", "avi", "mkv"])
        
        if uploaded_file is not None:
            # Save uploaded file temporarily
            temp_dir = tempfile.mkdtemp()
            temp_path = os.path.join(temp_dir, uploaded_file.name)
            
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            st.success(f"File uploaded: {uploaded_file.name}")
            st.video(temp_path)
            
            # Save to videos directory
            video_path = os.path.join("videos", uploaded_file.name)
            shutil.copy(temp_path, video_path)
            
            # Transcription options
            st.subheader("Transcription Options")
            whisper_model = st.selectbox("Whisper Model", ["tiny", "base", "small", "medium", "large"], index=1)
            
            # Process button
            if st.button("Transcribe Video"):
                with st.spinner("Extracting audio..."):
                    audio_path = os.path.join("audio", f"{os.path.splitext(uploaded_file.name)[0]}.wav")
                    if extract_audio(video_path, audio_path):
                        st.success("Audio extracted successfully")
                    else:
                        st.error("Failed to extract audio")
                        return
                
                with st.spinner("Transcribing audio with Whisper..."):
                    result = transcribe_audio(audio_path)
                    st.success("Transcription completed!")
                
                with st.spinner("Converting to SRT..."):
                    srt_content = convert_to_srt(result)
                    srt_path = os.path.join("captions", f"{os.path.splitext(uploaded_file.name)[0]}.srt")
                    
                    with open(srt_path, "w", encoding="utf-8") as f:
                        f.write(srt_content)
                    
                    st.session_state['srt_path'] = srt_path
                    st.session_state['srt_content'] = srt_content
                    st.session_state['video_path'] = video_path
                    
                    st.success(f"SRT file generated: {srt_path}")
                    
                    # Display preview of transcription
                    st.subheader("Transcription Preview")
                    st.text_area("SRT Content", srt_content, height=200)
            
            # Translation options
            if 'srt_content' in st.session_state:
                st.subheader("Translation Options")
                
                # OpenAI API Key
                api_key = st.text_input("OpenAI API Key", type="password")
                target_language = st.selectbox("Target Language", 
                                            ["Spanish", "French", "German", "Italian", "Portuguese", 
                                             "Russian", "Japanese", "Chinese", "Korean", "Arabic"])
                
                if st.button("Translate Captions") and api_key:
                    with st.spinner(f"Translating to {target_language}..."):
                        translated_srt = translate_srt_openai(st.session_state['srt_content'], api_key, target_language)
                        translated_srt_path = os.path.join("captions", f"{os.path.splitext(uploaded_file.name)[0]}_{target_language.lower()}.srt")
                        
                        with open(translated_srt_path, "w", encoding="utf-8") as f:
                            f.write(translated_srt)
                        
                        st.session_state['translated_srt_path'] = translated_srt_path
                        st.session_state['translated_srt_content'] = translated_srt
                        
                        st.success(f"Translated SRT generated: {translated_srt_path}")
                        
                        # Also convert to WebVTT
                        webvtt_content = srt_to_webvtt(translated_srt)
                        webvtt_path = os.path.join("captions", f"{os.path.splitext(uploaded_file.name)[0]}_{target_language.lower()}.vtt")
                        
                        with open(webvtt_path, "w", encoding="utf-8") as f:
                            f.write(webvtt_content)
                        
                        st.session_state['webvtt_path'] = webvtt_path
                        st.success(f"WebVTT file generated: {webvtt_path}")
                
                # Burn subtitles options
                st.subheader("Burn Subtitles into Video")
                subtitle_file = st.radio("Select Subtitle File", 
                                       ["Original", "Translated"] if 'translated_srt_path' in st.session_state else ["Original"],
                                       index=0)
                
                if st.button("Burn Subtitles into Video"):
                    with st.spinner("Burning subtitles into video..."):
                        if subtitle_file == "Original":
                            srt_to_use = st.session_state['srt_path']
                        else:
                            srt_to_use = st.session_state['translated_srt_path']
                        
                        output_name = f"{os.path.splitext(uploaded_file.name)[0]}_with_captions.mp4"
                        output_path = os.path.join("videos", output_name)
                        
                        if burn_subtitles(st.session_state['video_path'], srt_to_use, output_path):
                            st.session_state['output_video_path'] = output_path
                            st.success(f"Video with burned-in captions generated: {output_path}")
                        else:
                            st.error("Failed to burn subtitles into video")
    
    with tab2:
        st.header("View and Download Results")
        
        if 'srt_path' in st.session_state:
            st.subheader("Generated SRT")
            with open(st.session_state['srt_path'], "r", encoding="utf-8") as f:
                srt_content = f.read()
            st.download_button("Download SRT", srt_content, file_name=os.path.basename(st.session_state['srt_path']))
        
        if 'translated_srt_path' in st.session_state:
            st.subheader("Translated SRT")
            with open(st.session_state['translated_srt_path'], "r", encoding="utf-8") as f:
                translated_srt_content = f.read()
            st.download_button("Download Translated SRT", translated_srt_content, file_name=os.path.basename(st.session_state['translated_srt_path']))
        
        if 'webvtt_path' in st.session_state:
            st.subheader("WebVTT")
            with open(st.session_state['webvtt_path'], "r", encoding="utf-8") as f:
                webvtt_content = f.read()
            st.download_button("Download WebVTT", webvtt_content, file_name=os.path.basename(st.session_state['webvtt_path']))
        
        if 'output_video_path' in st.session_state:
            st.subheader("Video with Captions")
            st.video(st.session_state['output_video_path'])
            
            with open(st.session_state['output_video_path'], "rb") as f:
                video_bytes = f.read()
            st.download_button("Download Video with Captions", video_bytes, file_name=os.path.basename(st.session_state['output_video_path']))
    
    with tab3:
        st.header("Settings")
        
        st.subheader("OpenAI API")
        saved_api_key = st.text_input("Save OpenAI API Key for this session", type="password")
        if st.button("Save API Key") and saved_api_key:
            st.session_state['openai_api_key'] = saved_api_key
            st.success("API Key saved for this session")
        
        st.subheader("FFmpeg Path")
        ffmpeg_path = st.text_input("FFmpeg Executable Path (optional)", 
                                  value="ffmpeg" if os.name != "nt" else r"C:\ffmpeg-2025-03-24-git-cbbc927a67-essentials_build\bin\ffmpeg.exe")
        if st.button("Save FFmpeg Path") and ffmpeg_path:
            st.session_state['ffmpeg_path'] = ffmpeg_path
            st.success("FFmpeg path saved")
        
        st.subheader("Clear All Data")
        if st.button("Clear All Session Data", type="primary"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.success("All session data cleared")
            st.experimental_rerun()

if __name__ == "__main__":
    main()





