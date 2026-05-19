"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { buildApiHeaders, buildApiUrl } from "@/lib/api-client";

interface InputBarProps {
  onSend: (text: string) => void;
  isLoading: boolean;
}

interface AsrResponse {
  text?: string;
  error?: string;
}

interface SpeechRecognitionResultLike {
  readonly isFinal: boolean;
  readonly 0: { readonly transcript: string };
}

interface SpeechRecognitionEventLike {
  readonly resultIndex: number;
  readonly results: {
    readonly length: number;
    readonly [index: number]: SpeechRecognitionResultLike;
  };
}

interface NativeSpeechRecognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

interface NativeSpeechWindow extends Window {
  webkitSpeechRecognition?: new () => NativeSpeechRecognition;
  SpeechRecognition?: new () => NativeSpeechRecognition;
  webkitAudioContext?: typeof AudioContext;
}

type PressSource = "input" | "mic";

const LONG_PRESS_MS = 350;
const MOVE_TOLERANCE = 8;
const CANCEL_DISTANCE = 80;
const MAX_RECORDING_MS = 30_000;
const WAVE_COUNT = 26;

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const result = reader.result;
      if (typeof result !== "string") {
        reject(new Error("Failed to read audio"));
        return;
      }
      resolve(result.split(",")[1] ?? result);
    };
    reader.onerror = () => reject(new Error("Failed to read audio"));
    reader.readAsDataURL(blob);
  });
}

function pickMimeType(): string | undefined {
  const candidates = [
    "audio/mp4;codecs=mp4a.40.2",
    "audio/mp4",
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mpeg",
    "audio/wav",
  ];
  return candidates.find((type) => MediaRecorder.isTypeSupported(type));
}

function getPoint(e: React.TouchEvent | React.MouseEvent | TouchEvent | MouseEvent): { x: number; y: number } {
  if ("touches" in e && e.touches.length > 0) {
    return { x: e.touches[0].clientX, y: e.touches[0].clientY };
  }
  if ("changedTouches" in e && e.changedTouches.length > 0) {
    return { x: e.changedTouches[0].clientX, y: e.changedTouches[0].clientY };
  }
  return { x: (e as MouseEvent | React.MouseEvent).clientX, y: (e as MouseEvent | React.MouseEvent).clientY };
}

function vibrate(ms = 10) {
  navigator.vibrate?.(ms);
}

export default function InputBar({ onSend, isLoading }: InputBarProps) {
  const [inputText, setInputText] = useState("");
  const [voiceSupported, setVoiceSupported] = useState<boolean | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isPressPending, setIsPressPending] = useState(false);
  const [isCanceling, setIsCanceling] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState("");
  const [interimText, setInterimText] = useState("");
  const [dragOffset, setDragOffset] = useState(0);
  const [waveLevels, setWaveLevels] = useState(() => Array.from({ length: WAVE_COUNT }, () => 8));

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const recordingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const finishingRef = useRef(false);
  const isLoadingRef = useRef(isLoading);
  const isRecordingRef = useRef(false);
  const cancelingRef = useRef(false);
  const activePressRef = useRef<PressSource | null>(null);
  const startedAtRef = useRef(0);
  const startPointRef = useRef({ x: 0, y: 0 });
  const nativeTranscriptRef = useRef("");
  const recognitionRef = useRef<NativeSpeechRecognition | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const lastTouchAtRef = useRef(0);

  isLoadingRef.current = isLoading;
  isRecordingRef.current = isRecording;
  cancelingRef.current = isCanceling;

  useEffect(() => {
    const supported = typeof navigator !== "undefined" && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined";
    setVoiceSupported(supported);
    setVoiceStatus(supported ? "" : "当前浏览器不支持录音，请使用文字输入");
  }, []);

  const clearLongPressTimer = useCallback(() => {
    if (longPressTimerRef.current) {
      clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
    setIsPressPending(false);
  }, []);

  const stopVolumeMonitoring = useCallback(() => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    analyserRef.current = null;
    void audioContextRef.current?.close().catch(() => undefined);
    audioContextRef.current = null;
    setWaveLevels(Array.from({ length: WAVE_COUNT }, () => 8));
  }, []);

  const cleanupRecording = useCallback(() => {
    clearLongPressTimer();
    if (recordingTimerRef.current) {
      clearTimeout(recordingTimerRef.current);
      recordingTimerRef.current = null;
    }
    stopVolumeMonitoring();
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
    mediaRecorderRef.current = null;
    activePressRef.current = null;
    isRecordingRef.current = false;
    cancelingRef.current = false;
    setIsRecording(false);
    setIsCanceling(false);
    setIsPressPending(false);
    setDragOffset(0);
    document.body.classList.remove("voice-capture-active");
  }, [clearLongPressTimer, stopVolumeMonitoring]);

  const stopNativeSpeechRecognition = useCallback(() => {
    const recognition = recognitionRef.current;
    if (!recognition) return;
    recognition.onend = null;
    recognition.onerror = null;
    recognition.onresult = null;
    try {
      recognition.stop();
    } catch {
      try {
        recognition.abort();
      } catch {
        // Already stopped.
      }
    }
    recognitionRef.current = null;
  }, []);

  const startNativeSpeechRecognition = useCallback(() => {
    const SpeechRecognitionCtor =
      (window as NativeSpeechWindow).SpeechRecognition ?? (window as NativeSpeechWindow).webkitSpeechRecognition;
    if (!SpeechRecognitionCtor) return;

    try {
      const recognition = new SpeechRecognitionCtor();
      recognition.lang = "zh-CN";
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;
      nativeTranscriptRef.current = "";
      setInterimText("");

      recognition.onresult = (event) => {
        let finalText = "";
        let interim = "";
        for (let i = 0; i < event.results.length; i += 1) {
          const transcript = event.results[i][0].transcript;
          if (event.results[i].isFinal) {
            finalText += transcript;
          } else if (i >= event.resultIndex) {
            interim += transcript;
          }
        }
        const merged = `${finalText}${interim}`.trim();
        if (merged) {
          nativeTranscriptRef.current = merged;
          setInterimText(merged);
          setVoiceStatus(cancelingRef.current ? "松开取消" : "正在听你说话...");
        }
      };
      recognition.onerror = () => {
        nativeTranscriptRef.current = "";
      };
      recognition.onend = () => {
        recognitionRef.current = null;
      };
      recognition.start();
      recognitionRef.current = recognition;
    } catch {
      recognitionRef.current = null;
    }
  }, []);

  const startVolumeMonitoring = useCallback((stream: MediaStream) => {
    try {
      const AudioContextCtor = window.AudioContext ?? (window as NativeSpeechWindow).webkitAudioContext;
      if (!AudioContextCtor) return;
      const audioContext = new AudioContextCtor();
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      audioContext.createMediaStreamSource(stream).connect(analyser);
      audioContextRef.current = audioContext;
      analyserRef.current = analyser;
      const dataArray = new Uint8Array(analyser.frequencyBinCount);

      const update = () => {
        if (!isRecordingRef.current || !analyserRef.current) return;
        analyserRef.current.getByteFrequencyData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i += 1) sum += dataArray[i];
        const average = sum / dataArray.length;
        const level = Math.max(6, Math.min(34, 6 + (average / 128) * 28));
        setWaveLevels((prev) =>
          prev.map((_, index) => {
            const distance = Math.abs(index - prev.length / 2);
            const natural = Math.max(0.45, 1 - distance / prev.length);
            return Math.round(6 + level * natural * (0.75 + Math.random() * 0.35));
          }),
        );
        animationFrameRef.current = requestAnimationFrame(update);
      };
      update();
    } catch {
      // Waveform is decorative; recording should continue without it.
    }
  }, []);

  const waitForNativeTranscript = useCallback(async () => {
    for (let i = 0; i < 5; i += 1) {
      const text = nativeTranscriptRef.current.trim();
      if (text) return text;
      await new Promise((resolve) => setTimeout(resolve, 120));
    }
    return nativeTranscriptRef.current.trim();
  }, []);

  const insertRecognizedText = useCallback((text: string) => {
    const cleanText = text.trim();
    if (!cleanText) return;
    setInputText((prev) => `${prev}${cleanText}`);
    requestAnimationFrame(() => {
      const textarea = textareaRef.current;
      if (!textarea) return;
      textarea.focus();
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`;
      const len = textarea.value.length;
      textarea.setSelectionRange(len, len);
    });
  }, []);

  const submitAudio = useCallback(async (blob: Blob) => {
    if (blob.size < 800) {
      setVoiceStatus("录音时间太短，请重新按住说话");
      return;
    }
    setVoiceStatus("正在转文字...");
    try {
      const base64Data = await blobToBase64(blob);
      const mimeType = blob.type || "audio/webm";
      const resp = await fetch(buildApiUrl("/api/asr"), {
        method: "POST",
        headers: buildApiHeaders(),
        body: JSON.stringify({
          base64Data,
          base64_data: base64Data,
          mimeType,
          mime_type: mimeType,
        }),
      });
      const data = (await resp.json()) as AsrResponse;
      if (!resp.ok || data.error) {
        throw new Error(data.error ?? "ASR failed");
      }
      const text = data.text?.trim();
      if (text) {
        setVoiceStatus("");
        insertRecognizedText(text);
      } else {
        setVoiceStatus("没有听清，请再说一次");
      }
    } catch (error) {
      console.error("ASR error:", error);
      setVoiceStatus("语音识别失败，请稍后重试");
    }
  }, [insertRecognizedText]);

  const finishRecording = useCallback((discard = false) => {
    const recorder = mediaRecorderRef.current;
    if (!recorder || finishingRef.current) return;

    finishingRef.current = true;
    stopNativeSpeechRecognition();
    vibrate(discard ? 18 : 10);

    recorder.onstop = () => {
      const chunks = audioChunksRef.current;
      audioChunksRef.current = [];
      const mimeType = recorder.mimeType || "audio/webm";
      const shouldDiscard = discard || cancelingRef.current;
      cleanupRecording();
      finishingRef.current = false;

      void (async () => {
        if (shouldDiscard) {
          setVoiceStatus("已取消");
          window.setTimeout(() => setVoiceStatus(""), 900);
          return;
        }

        const nativeText = await waitForNativeTranscript();
        if (nativeText) {
          setVoiceStatus("");
          insertRecognizedText(nativeText);
          return;
        }

        await submitAudio(new Blob(chunks, { type: mimeType }));
      })();
    };

    if (recorder.state !== "inactive") {
      recorder.stop();
    } else {
      recorder.onstop(new Event("stop"));
    }
  }, [cleanupRecording, insertRecognizedText, stopNativeSpeechRecognition, submitAudio, waitForNativeTranscript]);

  const startRecording = useCallback(async () => {
    if (isLoadingRef.current || isRecordingRef.current || !voiceSupported) return;
    document.body.classList.add("voice-capture-active");
    vibrate(10);
    setVoiceStatus("正在听你说话...");
    setInterimText("");
    isRecordingRef.current = true;
    cancelingRef.current = false;
    setIsCanceling(false);
    setIsRecording(true);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = pickMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      audioChunksRef.current = [];
      mediaStreamRef.current = stream;
      mediaRecorderRef.current = recorder;
      finishingRef.current = false;
      nativeTranscriptRef.current = "";

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };
      recorder.onerror = () => {
        setVoiceStatus("录音失败，请检查麦克风权限");
        cleanupRecording();
      };

      recorder.start(300);
      startVolumeMonitoring(stream);
      startNativeSpeechRecognition();
      recordingTimerRef.current = setTimeout(() => finishRecording(false), MAX_RECORDING_MS);
    } catch (error) {
      console.error("MediaRecorder error:", error);
      setVoiceStatus("无法启动麦克风，请允许录音权限");
      cleanupRecording();
    }
  }, [cleanupRecording, finishRecording, startNativeSpeechRecognition, startVolumeMonitoring, voiceSupported]);

  const beginPress = useCallback((e: React.TouchEvent | React.MouseEvent, source: PressSource) => {
    if (isLoadingRef.current || !voiceSupported) return;
    if ("button" in e && e.button !== 0) return;
    if ("touches" in e) {
      lastTouchAtRef.current = Date.now();
    } else if (Date.now() - lastTouchAtRef.current < 700) {
      return;
    }
    e.preventDefault();
    e.stopPropagation();

    const point = getPoint(e);
    startPointRef.current = point;
    startedAtRef.current = Date.now();
    activePressRef.current = source;
    setIsCanceling(false);
    setDragOffset(0);

    if (source === "mic") {
      void startRecording();
      return;
    }

    clearLongPressTimer();
    setIsPressPending(true);
    longPressTimerRef.current = setTimeout(() => {
      longPressTimerRef.current = null;
      setIsPressPending(false);
      void startRecording();
    }, LONG_PRESS_MS);
  }, [clearLongPressTimer, startRecording, voiceSupported]);

  const movePress = useCallback((e: React.TouchEvent | React.MouseEvent | TouchEvent | MouseEvent) => {
    if (!activePressRef.current) return;
    const point = getPoint(e);
    const dx = Math.abs(point.x - startPointRef.current.x);
    const dy = point.y - startPointRef.current.y;

    if (longPressTimerRef.current && (dx > MOVE_TOLERANCE || Math.abs(dy) > MOVE_TOLERANCE)) {
      clearLongPressTimer();
      return;
    }

    if (!isRecordingRef.current) return;
    if ("preventDefault" in e) e.preventDefault();
    const upward = Math.max(0, -dy);
    const nextCanceling = upward > CANCEL_DISTANCE;
    setDragOffset(Math.min(upward, 132));
    cancelingRef.current = nextCanceling;
    setIsCanceling(nextCanceling);
    setVoiceStatus(nextCanceling ? "松开取消" : "正在听你说话...");
  }, [clearLongPressTimer]);

  const endPress = useCallback((e?: React.TouchEvent | React.MouseEvent | TouchEvent | MouseEvent) => {
    if (!activePressRef.current) return;
    e?.preventDefault();
    e?.stopPropagation();

    const source = activePressRef.current;
    const wasPending = Boolean(longPressTimerRef.current);
    clearLongPressTimer();

    if (!isRecordingRef.current) {
      activePressRef.current = null;
      if (source === "input" && wasPending) {
        requestAnimationFrame(() => {
          textareaRef.current?.focus();
          const len = textareaRef.current?.value.length ?? 0;
          textareaRef.current?.setSelectionRange(len, len);
        });
      }
      return;
    }

    finishRecording(cancelingRef.current);
  }, [clearLongPressTimer, finishRecording]);

  const cancelPress = useCallback(() => {
    clearLongPressTimer();
    if (isRecordingRef.current) finishRecording(true);
    activePressRef.current = null;
  }, [clearLongPressTimer, finishRecording]);

  useEffect(() => {
    if (!isRecording && !isPressPending) return undefined;

    const onTouchMove = (event: TouchEvent) => movePress(event);
    const onTouchEnd = (event: TouchEvent) => endPress(event);
    const onMouseMove = (event: MouseEvent) => movePress(event);
    const onMouseUp = (event: MouseEvent) => endPress(event);

    document.addEventListener("touchmove", onTouchMove, { passive: false });
    document.addEventListener("touchend", onTouchEnd, { passive: false });
    document.addEventListener("touchcancel", onTouchEnd, { passive: false });
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);

    return () => {
      document.removeEventListener("touchmove", onTouchMove);
      document.removeEventListener("touchend", onTouchEnd);
      document.removeEventListener("touchcancel", onTouchEnd);
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
  }, [endPress, isPressPending, isRecording, movePress]);

  useEffect(() => {
    return () => {
      clearLongPressTimer();
      stopNativeSpeechRecognition();
      cleanupRecording();
    };
  }, [cleanupRecording, clearLongPressTimer, stopNativeSpeechRecognition]);

  const handleSend = useCallback(() => {
    const text = inputText.trim();
    if (!text || isLoadingRef.current) return;
    onSend(text);
    setInputText("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }, [inputText, onSend]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  const handleInput = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputText(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, []);

  const handleTextareaTouchStart = useCallback((e: React.TouchEvent) => {
    beginPress(e, "input");
  }, [beginPress]);

  const toggleVoiceFromMic = useCallback((e: React.MouseEvent<HTMLButtonElement>) => {
    e.preventDefault();
    e.stopPropagation();
    if (isLoadingRef.current || !voiceSupported) return;
    if (isRecordingRef.current) {
      finishRecording(false);
      return;
    }
    activePressRef.current = null;
    cancelingRef.current = false;
    setDragOffset(0);
    setIsCanceling(false);
    void startRecording();
  }, [finishRecording, startRecording, voiceSupported]);

  const handleRecordingTouchStart = useCallback((e: React.TouchEvent | React.MouseEvent) => {
    if (!isRecordingRef.current || activePressRef.current) return;
    e.preventDefault();
    e.stopPropagation();
    const point = getPoint(e);
    startPointRef.current = point;
    startedAtRef.current = Date.now() - 1000;
    activePressRef.current = "mic";
  }, []);

  return (
    <>
      {voiceStatus && !isRecording && <div className="voice-hint-text">{voiceStatus}</div>}

      <div
        className={`recording-overlay ${isRecording ? "active" : ""} ${isCanceling ? "canceling" : ""}`}
        onMouseDown={handleRecordingTouchStart}
        onTouchStart={handleRecordingTouchStart}
      >
        <div className="recording-card">
          <div className="recording-status">{isCanceling ? "松开取消" : "正在听你说话..."}</div>
          <div className="recording-wave" aria-hidden="true">
            {waveLevels.map((height, index) => (
              <span key={index} style={{ height }} />
            ))}
          </div>
          <button
            type="button"
            className={`recording-mic ${isCanceling ? "canceling" : ""}`}
            style={{ transform: `translateY(-${dragOffset}px)` }}
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              finishRecording(false);
            }}
            aria-label="结束语音输入"
          >
            <svg viewBox="0 0 24 24">
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8" />
            </svg>
          </button>
          <div className="recording-interim">{interimText || "松开结束，上滑取消"}</div>
        </div>
      </div>

      <div className={`input-area ${isRecording ? "recording" : ""} ${isPressPending ? "pending" : ""}`}>
        <div
          className={`input-field ${isRecording ? "recording" : ""}`}
          onMouseDown={(e) => beginPress(e, "input")}
          onContextMenu={(e) => e.preventDefault()}
        >
          <textarea
            ref={textareaRef}
            className="input-box"
            placeholder={isRecording ? "松手发送，上移取消" : "说说孩子最近让你最头疼的一件事"}
            value={inputText}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            onTouchStart={handleTextareaTouchStart}
            onContextMenu={(e) => e.preventDefault()}
            rows={1}
            readOnly={isRecording || isPressPending}
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck={false}
          />
          {(isPressPending || isRecording) && (
            <div className="voice-press-hint">{isRecording ? "松开结束，上滑取消" : "继续按住开始语音"}</div>
          )}
        </div>

        {inputText.trim() ? (
          <button
            type="button"
            className="send-icon-btn"
            onClick={handleSend}
            disabled={isLoading}
            aria-label="发送"
          >
            <svg viewBox="0 0 24 24">
              <path d="M5 12h14" />
              <path d="M13 6l6 6-6 6" />
            </svg>
          </button>
        ) : voiceSupported ? (
          <button
            type="button"
            className={`input-tool-btn ${isRecording ? "recording" : ""}`}
            onClick={toggleVoiceFromMic}
            onContextMenu={(e) => e.preventDefault()}
            disabled={isLoading}
            aria-label={isRecording ? "结束语音输入" : "开始语音输入"}
          >
            <svg viewBox="0 0 24 24">
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v4M8 23h8" />
            </svg>
          </button>
        ) : null}

        <button type="button" className="input-tool-btn input-plus-btn" aria-label="更多">
          <svg viewBox="0 0 24 24">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>
      </div>
    </>
  );
}
