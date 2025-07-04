import click
import logging
from .processor import process_articles
from .common import (
    generate_lowercase_string,
    validate_models,
    validate_voice,
    process_text_to_audio,
)
from .condense import condense_text
from .models import ProcessingResult
from typing import List

logger = logging.getLogger(__name__)

@click.command()
@click.option("--url", type=str, help="URL of the article to be fetched.")
@click.option(
    "--vendor",
    type=click.Choice(["openai", "elevenlabs"]),
    default="openai",
    help="Choose vendor to use to convert text to audio.",
)
@click.option(
    "--file-url-list",
    type=click.Path(exists=True, dir_okay=False, readable=True),
    help="Path to a file with URLs placed on every new line.",
)
@click.option(
    "--file-text",
    type=click.Path(exists=True, dir_okay=False, readable=True),
    help="Path to a file with text to be sent over to AI vendor. This is currently a workaround of Cloudflare blocking.",
)
@click.option(
    "--directory",
    type=click.Path(exists=False, file_okay=False, writable=True),
    default=".",
    help="Directory where the output audio file will be saved. The filename will be derived from the article title.",
)
@click.option(
    "--speech-model",
    callback=validate_models,
    default=None,
    help="The model to be used for text-to-speech conversion (e.g., tts-1, eleven_monolingual_v1)",
)
@click.option(
    "--text-model",
    type=str,
    default="gpt-4-turbo-preview",
    help="The model to be used for text condensing (e.g., gpt-4-turbo-preview, gpt-3.5-turbo)",
)
@click.option(
    "--voice",
    callback=validate_voice,
    default=None,
    help="""
    OpenIA voices: alloy, echo, fable, onyx, nova, shimmer;
    ElevenLabs voices: Sarah.
    """,
)
@click.option(
    "--strip",
    type=click.IntRange(5, 2000),
    help="By what number of chars to strip the text to send to OpenAI.",
)
@click.option(
    "--audio-format",
    type=click.Choice(["mp3", "opus", "aac", "flac", "pcm"]),
    default="mp3",
    help="The audio format for the output file. Default is mp3.",
)
@click.option("--yes", is_flag=True, help="Automatically answer yes to all prompts")
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.option(
    "--condense",
    is_flag=True,
    help="Condense the article before converting to audio",
)
@click.option(
    "--condense-ratio",
    type=click.FloatRange(0.1, 1.0),
    default=0.2,
    help="Ratio to condense the text (0.2 = 20% of original length)",
)
@click.option(
    "--abs-url",
    type=str,
    help="Audiobookshelf server URL for uploading audio files",
)
@click.option(
    "--abs-pod-lib-id",
    type=str,
    help="Audiobookshelf podcast library ID",
)
@click.option(
    "--abs-pod-folder-id",
    type=str,
    help="Audiobookshelf podcast folder ID",
)
def cli(
    vendor,
    url,
    file_url_list,
    file_text,
    directory,
    audio_format,
    speech_model,
    text_model,
    voice,
    strip,
    yes,
    debug,
    condense,
    condense_ratio,
    abs_url,
    abs_pod_lib_id,
    abs_pod_folder_id,
):
    # Set up logging
    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)

    logger.debug("Starting CLI with options: %s", locals())

    if not url and not file_url_list and not file_text:
        raise click.UsageError(
            "You must provide either --url, --file-url-list or --file-text."
        )

    # Validate Audiobookshelf arguments - all or none must be provided
    abs_args = [abs_url, abs_pod_lib_id, abs_pod_folder_id]
    abs_provided = [arg for arg in abs_args if arg is not None]
    
    if abs_provided and len(abs_provided) != 3:
        missing_args = []
        if not abs_url:
            missing_args.append("--abs-url")
        if not abs_pod_lib_id:
            missing_args.append("--abs-pod-lib-id")
        if not abs_pod_folder_id:
            missing_args.append("--abs-pod-folder-id")
        
        raise click.UsageError(
            f"When using Audiobookshelf integration, all three arguments must be provided: "
            f"--abs-url, --abs-pod-lib-id, --abs-pod-folder-id. Missing: {', '.join(missing_args)}"
        )

    # Set model and voice based on the API vendor
    if vendor == "elevenlabs":
        speech_model = speech_model or "eleven_monolingual_v1"
        voice = voice or "Sarah"
    elif vendor == "openai":
        speech_model = speech_model or "tts-1"
        voice = voice or "alloy"

    logger.debug(
        "Using vendor: %s, speech_model: %s, voice: %s", vendor, speech_model, voice
    )
    if condense:
        logger.debug("Using text_model: %s", text_model)

    if file_text:
        with open(file_text, "r") as f:
            text = f.read()
        if condense:
            logger.info("Condensing text...")
            text = condense_text(text, text_model, condense_ratio)
        title = f"custom-text-podcast-{generate_lowercase_string()}"
        logger.info(f"Processing custom text with title: {title}")
        process_text_to_audio(
            text, title, vendor, directory, audio_format, speech_model, voice, strip,
            abs_url, abs_pod_lib_id, abs_pod_folder_id
        )
    else:
        urls = []
        if url:
            urls.append(url)
        if file_url_list:
            with open(file_url_list, "r") as f:
                urls.extend([line.strip() for line in f if line.strip()])

        # Create kwargs dict explicitly instead of using locals()
        kwargs = {
            'vendor': vendor,
            'directory': directory,
            'audio_format': audio_format,
            'speech_model': speech_model,
            'text_model': text_model,
            'voice': voice,
            'strip': strip,
            'yes': yes,
            'debug': debug,
            'condense': condense,
            'condense_ratio': condense_ratio,
            'abs_url': abs_url,
            'abs_pod_lib_id': abs_pod_lib_id,
            'abs_pod_folder_id': abs_pod_folder_id,
        }
        
        results = process_articles(urls, **kwargs)
        
        # Remove successfully processed URLs from the file
        if file_url_list and results:
            successful_urls = {result.url for result in results if result.success}
            if successful_urls:
                with open(file_url_list, "r") as f:
                    lines = f.readlines()
                
                with open(file_url_list, "w") as f:
                    for line in lines:
                        url = line.strip()
                        if url not in successful_urls:
                            f.write(line)
                
                logger.info(f"Removed {len(successful_urls)} successfully processed URLs from {file_url_list}")


if __name__ == "__main__":
    cli()
