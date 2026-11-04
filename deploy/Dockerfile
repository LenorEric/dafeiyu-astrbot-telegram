FROM soulter/astrbot:v4.29.0
COPY deploy/bili_activity/requirements.txt /tmp/activity-requirements.txt
RUN --mount=type=secret,id=proxy_ca,target=/run/proxy-ca.pem \
    if [ -f /run/proxy-ca.pem ]; then export PIP_CERT=/run/proxy-ca.pem; fi; \
    pip install --no-cache-dir -r /tmp/activity-requirements.txt edge-tts imageio-ffmpeg
# Keep source, licenses and patches together; one COPY avoids redundant VFS layers.
COPY . /opt/dafeiyu
RUN cp /opt/dafeiyu/deploy/patches/chat_layout.py /AstrBot/astrbot/core/pipeline/chat_layout.py && \
    cp /opt/dafeiyu/deploy/patches/stage.py /AstrBot/astrbot/core/pipeline/result_decorate/stage.py && \
    cp /opt/dafeiyu/deploy/patches/respond_stage.py /AstrBot/astrbot/core/pipeline/respond/stage.py && \
    cp /opt/dafeiyu/deploy/patches/dashscope_tts.py /AstrBot/astrbot/core/provider/sources/dashscope_tts.py
