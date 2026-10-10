/*
 * SPDX-License-Identifier: GPL-3.0-only
 * MuseScore-Studio-CLA-applies
 *
 * MuseScore Studio
 * Music Composition & Notation
 *
 * Copyright (C) 2026 DB Score contributors
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 3 as
 * published by the Free Software Foundation.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */
#include "AudioTrackSettingsModel.h"

#include <algorithm>
#include <complex>
#include <cmath>
#include <thread>
#include <vector>

#include <QFile>
#include <QFileInfo>
#include <QPointer>

#include "log.h"
#include "notation/imasternotation.h"
#include "notation/inotationplayback.h"
#include "project/inotationproject.h"

#include "audio/engine/internal/codecs/thirdparty/dr_mp3.h"
#include "audio/engine/internal/codecs/thirdparty/dr_flac.h"

using namespace mu::project;

namespace {
bool computeWavPeaks(const QString& path, double& duration, QVariantList& peaks, int buckets = 2048)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) {
        return false;
    }

    const QByteArray bytes = file.readAll();
    if (bytes.size() < 44 || bytes.left(4) != "RIFF" || bytes.mid(8, 4) != "WAVE") {
        return false;
    }

    int pos = 12;
    int audioFormat = 0;
    int channels = 0;
    int sampleRate = 0;
    int bitsPerSample = 0;
    int dataSize = 0;
    int dataOffset = 0;

    while (pos + 8 <= bytes.size()) {
        const QByteArray id = bytes.mid(pos, 4);
        const int size = int(bytes[pos + 4] & 0xff)
                         | (int(bytes[pos + 5] & 0xff) << 8)
                         | (int(bytes[pos + 6] & 0xff) << 16)
                         | (int(bytes[pos + 7] & 0xff) << 24);
        if (id == "fmt ") {
            if (pos + 24 > bytes.size()) {
                return false;
            }
            audioFormat = int(bytes[pos + 8] & 0xff) | (int(bytes[pos + 9] & 0xff) << 8);
            channels = int(bytes[pos + 10] & 0xff) | (int(bytes[pos + 11] & 0xff) << 8);
            sampleRate = int(bytes[pos + 12] & 0xff) | (int(bytes[pos + 13] & 0xff) << 8)
                         | (int(bytes[pos + 14] & 0xff) << 16) | (int(bytes[pos + 15] & 0xff) << 24);
            bitsPerSample = int(bytes[pos + 22] & 0xff) | (int(bytes[pos + 23] & 0xff) << 8);
            pos += 8 + size + (size & 1);
        } else if (id == "data") {
            dataSize = size;
            dataOffset = pos + 8;
            break;
        } else {
            pos += 8 + size + (size & 1);
        }
    }

    if (audioFormat != 1 || channels <= 0 || sampleRate <= 0 || bitsPerSample <= 0 || dataSize <= 0) {
        return false;
    }

    const int bytesPerSample = bitsPerSample / 8;
    const int frames = dataSize / (channels * bytesPerSample);
    if (frames <= 0) {
        return false;
    }

    duration = double(frames) / sampleRate;
    const int bucketCount = std::min(buckets, frames);
    peaks.clear();
    peaks.reserve(bucketCount);

    const char* data = bytes.constData() + dataOffset;
    for (int b = 0; b < bucketCount; ++b) {
        const int startFrame = (b * frames) / bucketCount;
        const int endFrame = ((b + 1) * frames) / bucketCount;
        float minV = 0.f;
        float maxV = 0.f;
        for (int f = startFrame; f < endFrame; ++f) {
            for (int c = 0; c < channels; ++c) {
                const int sampleIndex = (f * channels + c) * bytesPerSample;
                if (sampleIndex + bytesPerSample > dataSize) {
                    break;
                }
                float value = 0.f;
                if (bitsPerSample == 16) {
                    const unsigned char* p = reinterpret_cast<const unsigned char*>(data + sampleIndex);
                    short s = short(p[0]) | (short(p[1]) << 8);
                    value = float(s) / 32768.f;
                } else if (bitsPerSample == 8) {
                    const unsigned char v = static_cast<unsigned char>(data[sampleIndex]);
                    value = (float(v) / 255.f) * 2.f - 1.f;
                } else if (bitsPerSample == 24) {
                    const unsigned char* p = reinterpret_cast<const unsigned char*>(data + sampleIndex);
                    int32_t s = int32_t(p[0]) | (int32_t(p[1]) << 8) | (int32_t(p[2]) << 16);
                    if (s & 0x800000) {
                        s |= ~0xffffff;
                    }
                    value = float(s) / 8388608.f;
                } else if (bitsPerSample == 32) {
                    const unsigned char* p = reinterpret_cast<const unsigned char*>(data + sampleIndex);
                    int32_t s = int32_t(p[0]) | (int32_t(p[1]) << 8) | (int32_t(p[2]) << 16) | (int32_t(p[3]) << 24);
                    value = float(double(s) / 2147483648.0);
                } else {
                    continue;
                }
                minV = std::min(minV, value);
                maxV = std::max(maxV, value);
            }
        }
        QVariantMap item;
        item.insert("min", minV);
        item.insert("max", maxV);
        peaks.append(item);
    }

    return true;
}

bool computeMp3Peaks(const QString& path, double& duration, QVariantList& peaks, int buckets = 2048)
{
    drmp3 mp3;
    if (!drmp3_init_file(&mp3, path.toUtf8().constData(), nullptr)) {
        return false;
    }

    const uint64_t totalFrames = drmp3_get_pcm_frame_count(&mp3);
    const unsigned int channels = mp3.channels;
    const unsigned int sampleRate = mp3.sampleRate;
    if (totalFrames == 0 || channels == 0 || sampleRate == 0) {
        drmp3_uninit(&mp3);
        return false;
    }

    std::vector<float> samples(totalFrames * channels);
    const uint64_t read = drmp3_read_pcm_frames_f32(&mp3, totalFrames, samples.data());
    drmp3_uninit(&mp3);

    if (read == 0) {
        return false;
    }

    //! NOTE: for VBR files the frame count can be an over-estimate; use the frames we
    //! actually decoded so the waveform matches the real audio length.
    const uint64_t actualFrames = read;

    duration = double(actualFrames) / sampleRate;
    const int bucketCount = std::min(buckets, int(actualFrames));
    peaks.clear();
    peaks.reserve(bucketCount);

    for (int b = 0; b < bucketCount; ++b) {
        const int startFrame = int((uint64_t(b) * actualFrames) / bucketCount);
        const int endFrame = int((uint64_t(b + 1) * actualFrames) / bucketCount);
        float minV = 0.f;
        float maxV = 0.f;
        for (int f = startFrame; f < endFrame; ++f) {
            for (unsigned int c = 0; c < channels; ++c) {
                const size_t index = size_t(f) * channels + c;
                if (index < samples.size()) {
                    const float v = samples[index];
                    minV = std::min(minV, v);
                    maxV = std::max(maxV, v);
                }
            }
        }
        QVariantMap item;
        item.insert("min", minV);
        item.insert("max", maxV);
        peaks.append(item);
    }

    return true;
}

bool computeFlacPeaks(const QString& path, double& duration, QVariantList& peaks, int buckets = 2048)
{
    drflac* flac = drflac_open_file(path.toUtf8().constData(), nullptr);
    if (!flac) {
        return false;
    }

    const uint64_t totalFrames = flac->totalPCMFrameCount;
    const unsigned int channels = flac->channels;
    const unsigned int sampleRate = flac->sampleRate;
    if (totalFrames == 0 || channels == 0 || sampleRate == 0) {
        drflac_close(flac);
        return false;
    }

    std::vector<float> samples(totalFrames * channels);
    const uint64_t read = drflac_read_pcm_frames_f32(flac, totalFrames, samples.data());
    drflac_close(flac);

    if (read == 0) {
        return false;
    }

    const uint64_t actualFrames = read;
    duration = double(actualFrames) / sampleRate;
    const int bucketCount = std::min(buckets, int(actualFrames));
    peaks.clear();
    peaks.reserve(bucketCount);

    for (int b = 0; b < bucketCount; ++b) {
        const int startFrame = int((uint64_t(b) * actualFrames) / bucketCount);
        const int endFrame = int((uint64_t(b + 1) * actualFrames) / bucketCount);
        float minV = 0.f;
        float maxV = 0.f;
        for (int f = startFrame; f < endFrame; ++f) {
            for (unsigned int c = 0; c < channels; ++c) {
                const size_t index = size_t(f) * channels + c;
                if (index < samples.size()) {
                    const float v = samples[index];
                    minV = std::min(minV, v);
                    maxV = std::max(maxV, v);
                }
            }
        }
        QVariantMap item;
        item.insert("min", minV);
        item.insert("max", maxV);
        peaks.append(item);
    }

    return true;
}

bool decodeWavMono(const QString& path, std::vector<float>& mono, unsigned int& sampleRate)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) {
        return false;
    }

    const QByteArray bytes = file.readAll();
    if (bytes.size() < 44 || bytes.left(4) != "RIFF" || bytes.mid(8, 4) != "WAVE") {
        return false;
    }

    int pos = 12;
    int audioFormat = 0;
    int channels = 0;
    int bitsPerSample = 0;
    int dataSize = 0;
    int dataOffset = 0;

    while (pos + 8 <= bytes.size()) {
        const QByteArray id = bytes.mid(pos, 4);
        const int size = int(bytes[pos + 4] & 0xff) | (int(bytes[pos + 5] & 0xff) << 8)
                         | (int(bytes[pos + 6] & 0xff) << 16) | (int(bytes[pos + 7] & 0xff) << 24);
        if (id == "fmt ") {
            audioFormat = int(bytes[pos + 8] & 0xff) | (int(bytes[pos + 9] & 0xff) << 8);
            channels = int(bytes[pos + 10] & 0xff) | (int(bytes[pos + 11] & 0xff) << 8);
            sampleRate = int(bytes[pos + 12] & 0xff) | (int(bytes[pos + 13] & 0xff) << 8)
                         | (int(bytes[pos + 14] & 0xff) << 16) | (int(bytes[pos + 15] & 0xff) << 24);
            bitsPerSample = int(bytes[pos + 22] & 0xff) | (int(bytes[pos + 23] & 0xff) << 8);
            pos += 8 + size + (size & 1);
        } else if (id == "data") {
            dataSize = size;
            dataOffset = pos + 8;
            break;
        } else {
            pos += 8 + size + (size & 1);
        }
    }

    if (audioFormat != 1 || channels <= 0 || sampleRate == 0 || bitsPerSample <= 0 || dataSize <= 0) {
        return false;
    }

    const int bytesPerSample = bitsPerSample / 8;
    const int frames = dataSize / (channels * bytesPerSample);
    if (frames <= 0) {
        return false;
    }

    const char* data = bytes.constData() + dataOffset;
    mono.resize(frames);
    for (int f = 0; f < frames; ++f) {
        float acc = 0.f;
        for (int c = 0; c < channels; ++c) {
            const unsigned char* p = reinterpret_cast<const unsigned char*>(data + (f * channels + c) * bytesPerSample);
            float v = 0.f;
            if (bitsPerSample == 16) {
                short s = short(p[0]) | (short(p[1]) << 8);
                v = float(s) / 32768.f;
            } else if (bitsPerSample == 8) {
                v = (float(p[0]) / 255.f) * 2.f - 1.f;
            } else {
                continue;
            }
            acc += v;
        }
        mono[f] = acc / channels;
    }
    return true;
}

bool decodeMp3Mono(const QString& path, std::vector<float>& mono, unsigned int& sampleRate)
{
    drmp3 mp3;
    if (!drmp3_init_file(&mp3, path.toUtf8().constData(), nullptr)) {
        return false;
    }

    const uint64_t estimatedFrames = drmp3_get_pcm_frame_count(&mp3);
    const unsigned int channels = mp3.channels;
    sampleRate = mp3.sampleRate;
    if (estimatedFrames == 0 || channels == 0 || sampleRate == 0) {
        drmp3_uninit(&mp3);
        return false;
    }

    std::vector<float> interleaved(estimatedFrames * channels);
    const uint64_t read = drmp3_read_pcm_frames_f32(&mp3, estimatedFrames, interleaved.data());
    drmp3_uninit(&mp3);

    //! NOTE: for VBR files the frame count can be an over-estimate; use the frames we
    //! actually decoded so the tempo estimate matches the real audio length.
    const uint64_t actualFrames = read;
    if (actualFrames == 0) {
        return false;
    }

    mono.resize(actualFrames);
    for (uint64_t f = 0; f < actualFrames; ++f) {
        float acc = 0.f;
        for (unsigned int c = 0; c < channels; ++c) {
            acc += interleaved[f * channels + c];
        }
        mono[f] = acc / float(channels);
    }
    return true;
}

bool decodeFlacMono(const QString& path, std::vector<float>& mono, unsigned int& sampleRate)
{
    drflac* flac = drflac_open_file(path.toUtf8().constData(), nullptr);
    if (!flac) {
        return false;
    }

    const uint64_t frames = flac->totalPCMFrameCount;
    const unsigned int channels = flac->channels;
    sampleRate = flac->sampleRate;
    if (frames == 0 || channels == 0 || sampleRate == 0) {
        drflac_close(flac);
        return false;
    }

    std::vector<float> interleaved(frames * channels);
    const uint64_t read = drflac_read_pcm_frames_f32(flac, frames, interleaved.data());
    drflac_close(flac);

    const uint64_t actualFrames = read;
    if (actualFrames == 0) {
        return false;
    }

    mono.resize(actualFrames);
    for (uint64_t f = 0; f < actualFrames; ++f) {
        float acc = 0.f;
        for (unsigned int c = 0; c < channels; ++c) {
            acc += interleaved[f * channels + c];
        }
        mono[f] = acc / float(channels);
    }
    return true;
}

// ---------------------------------------------------------------------------
// Tempo (BPM) detection
//
// MuseScore's tempo unit is "quarter notes per minute" (crotchets per minute),
// independent of the time signature. The detector reports the same quarter-note
// rate so the measured value can be entered directly as a MuseScore tempo and the
// beat grid stays aligned.
//
// Pipeline (deterministic, no external dependencies):
//   1. short-time Fourier transform -> half-wave rectified spectral flux
//      (onset-strength envelope)
//   2. normalized autocorrelation of the onset envelope
//   3. comb-filter bank over candidate beat periods (harmonic sum)
//   4. log-normal "tactus" prior centred on 120 BPM (disambiguates octave errors,
//      e.g. 70 vs 140 BPM, by gently preferring the quarter-note rate closest to 120)
//   5. dense tempo scan (0.01 BPM steps) for two-decimal-place resolution
// ---------------------------------------------------------------------------

constexpr double kPi = 3.14159265358979323846;

// Iterative in-place radix-2 FFT. `n` must be a power of two.
void fftRadix2(std::vector<std::complex<float>>& a, bool inverse)
{
    const int n = int(a.size());
    for (int i = 1, j = 0; i < n; ++i) {
        int bit = n >> 1;
        for (; j & bit; bit >>= 1) {
            j ^= bit;
        }
        j ^= bit;
        if (i < j) {
            std::swap(a[i], a[j]);
        }
    }
    for (int len = 2; len <= n; len <<= 1) {
        const double ang = (inverse ? -2.0 : 2.0) * kPi / double(len);
        const std::complex<float> wlen(std::cos(ang), std::sin(ang));
        for (int i = 0; i < n; i += len) {
            std::complex<float> w(1.0f, 0.0f);
            for (int j = 0; j < len / 2; ++j) {
                const std::complex<float> u = a[i + j];
                const std::complex<float> v = a[i + j + len / 2] * w;
                a[i + j] = u + v;
                a[i + j + len / 2] = u - v;
                w *= wlen;
            }
        }
    }
    if (inverse) {
        for (auto& x : a) {
            x /= float(n);
        }
    }
}

void computeSpectralFluxOnset(const std::vector<float>& mono, unsigned int sampleRate,
                              std::vector<float>& onset, double& frameRate)
{
    onset.clear();
    frameRate = 0.0;
    if (mono.empty() || sampleRate == 0) {
        return;
    }

    // ~10 ms hop, ~23 ms Hann window (power-of-two FFT size).
    const int hop = std::max<int>(1, int(sampleRate / 100));
    int fftSize = 1;
    while (fftSize < int(sampleRate * 0.023)) {
        fftSize <<= 1;
    }
    const int halfSize = fftSize / 2;

    std::vector<float> window(fftSize);
    for (int i = 0; i < fftSize; ++i) {
        window[i] = 0.5f * (1.0f - std::cos(2.0 * kPi * double(i) / double(fftSize - 1)));
    }

    std::vector<float> prevMag(halfSize + 1, 0.0f);
    std::vector<std::complex<float>> frame(fftSize);

    const size_t total = mono.size();
    const size_t frameCount = (total >= size_t(fftSize)) ? ((total - fftSize) / size_t(hop) + 1) : 0;
    onset.reserve(frameCount);

    for (size_t f = 0; f < frameCount; ++f) {
        const size_t base = f * size_t(hop);
        for (int i = 0; i < fftSize; ++i) {
            frame[i] = std::complex<float>(mono[base + size_t(i)] * window[i], 0.0f);
        }
        fftRadix2(frame, false);

        if (f == 0) {
            for (int k = 0; k <= halfSize; ++k) {
                prevMag[k] = std::abs(frame[k]);
            }
            onset.push_back(0.0f);
            continue;
        }

        float flux = 0.0f;
        for (int k = 0; k <= halfSize; ++k) {
            const float mag = std::abs(frame[k]);
            const float d = mag - prevMag[k];
            if (d > 0.0f) {
                flux += d;
            }
            prevMag[k] = mag;
        }
        onset.push_back(flux);
    }

    frameRate = double(sampleRate) / double(hop);
}

double detectBpm(const std::vector<float>& mono, unsigned int sampleRate)
{
    if (mono.size() < size_t(sampleRate) || sampleRate == 0) {
        return 0.0;
    }

    std::vector<float> flux;
    double frameRate = 0.0;
    computeSpectralFluxOnset(mono, sampleRate, flux, frameRate);
    if (flux.size() < 64 || frameRate <= 0.0) {
        return 0.0;
    }

    // Light 3-tap smoothing to suppress frame-to-frame noise.
    std::vector<float> onset(flux.size(), 0.0f);
    for (size_t i = 0; i < flux.size(); ++i) {
        float s = flux[i];
        int n = 1;
        if (i > 0) {
            s += flux[i - 1];
            ++n;
        }
        if (i + 1 < flux.size()) {
            s += flux[i + 1];
            ++n;
        }
        onset[i] = s / float(n);
    }

    // Remove the mean so autocorrelation measures periodicity, not loudness.
    double mean = 0.0;
    for (float v : onset) {
        mean += double(v);
    }
    mean /= double(onset.size());
    for (float& v : onset) {
        v -= float(mean);
    }

    constexpr double kMinBpm = 40.0;
    constexpr double kMaxBpm = 240.0;

    // Analyse up to six seconds of lag so that even the slowest tempo (40 BPM) still
    // has all four comb harmonics available inside the autocorrelation window.
    const int maxLag = std::min<int>(int(onset.size()) - 2, int(frameRate * 6.0));
    if (maxLag < 40) {
        return 0.0;
    }

    double r0 = 0.0;
    for (float v : onset) {
        r0 += double(v) * double(v);
    }
    if (r0 <= 0.0) {
        return 0.0;
    }

    // Normalized autocorrelation.
    std::vector<double> nacf(maxLag + 1, 0.0);
    for (int lag = 1; lag <= maxLag; ++lag) {
        double s = 0.0;
        const int n = int(onset.size()) - lag;
        for (int i = 0; i < n; ++i) {
            s += double(onset[i]) * double(onset[i + lag]);
        }
        nacf[lag] = s / r0;
    }

    // Comb-filter bank with a fixed number of harmonics and a fixed normalization so
    // the score is a smooth function of tempo (no hard tap-count discontinuities).
    constexpr double kGamma = 0.8;
    constexpr int kHarmonics = 4;
    double combWeights[kHarmonics];
    double combWeightSum = 0.0;
    {
        double w = 1.0;
        for (int k = 0; k < kHarmonics; ++k) {
            combWeights[k] = w;
            combWeightSum += w;
            w *= kGamma;
        }
    }

    // Linear interpolation of the normalized autocorrelation at a fractional lag.
    const auto acfAt = [&](double lag) -> double {
        if (lag <= 0.0 || lag > double(maxLag)) {
            return 0.0;
        }
        const int lo = int(std::floor(lag));
        if (lo >= maxLag) {
            return nacf[maxLag];
        }
        const double frac = lag - double(lo);
        return nacf[lo] * (1.0 - frac) + nacf[lo + 1] * frac;
    };

    constexpr double kPriorSigma = 1.2; // octaves
    const auto scoreAtBpm = [&](double bpm) -> double {
        const double tau = frameRate * 60.0 / bpm;
        double s = 0.0;
        for (int k = 1; k <= kHarmonics; ++k) {
            s += acfAt(double(k) * tau) * combWeights[k - 1];
        }
        const double comb = s / combWeightSum;

        // Log-normal tactus prior centred on 120 BPM. It disambiguates octave errors
        // (e.g. 70 vs 140 BPM) by gently preferring the quarter-note rate closest to
        // 120, without overriding strong evidence for very slow or very fast tempos.
        const double octaves = std::log2(bpm / 120.0);
        const double prior = std::exp(-0.5 * (octaves / kPriorSigma) * (octaves / kPriorSigma));
        return comb * prior;
    };

    // Dense scan gives 0.01 BPM resolution (two decimal places) directly.
    double bestBpm = 0.0;
    double bestScore = -1.0;
    for (double bpm = kMinBpm; bpm <= kMaxBpm + 1e-9; bpm += 0.01) {
        const double sc = scoreAtBpm(bpm);
        if (sc > bestScore) {
            bestScore = sc;
            bestBpm = bpm;
        }
    }

    if (bestBpm <= 0.0 || bestScore <= 0.0 || !std::isfinite(bestBpm)) {
        return 0.0;
    }
    return bestBpm;
}
}

AudioTrackSettingsModel::AudioTrackSettingsModel(QObject* parent)
    : QObject(parent), muse::Contextable(muse::iocCtxForQmlObject(this))
{
}

void AudioTrackSettingsModel::load()
{
    m_metronomeEnabled = notationConfiguration()->isMetronomeEnabled();
    if (!m_volumeInitialized) {
        m_masterVolumeDb = audioSettings() ? audioSettings()->masterAudioOutputParams().volume.to_double() : 0.0;
        m_scoreVolumeDb = 0.0;
        m_volumeInitialized = true;
    }

    if (!m_projectSubscribed) {
        globalContext()->currentProjectChanged().onNotify(this, [this]() {
            //! NOTE: A new project means a new ProjectAudioSettings instance and a new
            //! playback state, so the previous subscriptions must be rebuilt.
            m_settingsSubscribed = false;
            m_playbackSubscribed = false;
            load();
        });
        m_projectSubscribed = true;
    }

    subscribeOnPlayback();

    const IProjectAudioSettingsPtr settings = audioSettings();
    if (!settings) {
        return;
    }

    subscribeOnPlayback();

    if (!m_settingsSubscribed) {
        settings->audioTrackSettingsChanged().onNotify(this, [this]() {
            load();
        });
        m_settingsSubscribed = true;
    }

    const QString previousPath = firstClip() ? firstClip()->filePath.toQString() : QString();

    m_settings = settings->audioTrackSettings();

    //! NOTE: re-read the waveform only when the source file actually changed. For
    //! speed/volume/mute changes the source length and peaks are unchanged, and only
    //! the effective (stretched) length below changes.
    const AudioClipSettings* clip = firstClip();
    const QString newPath = clip ? clip->filePath.toQString() : QString();
    if (newPath != previousPath) {
        m_duration = 0.0;
        updateWaveform();
    }

    notifyAll();
    updateScoreBeatGrid();
}

void AudioTrackSettingsModel::subscribeOnPlayback()
{
    if (m_playbackSubscribed) {
        return;
    }

    const context::IPlaybackStatePtr state = globalContext()->playbackState();
    if (!state) {
        return;
    }

    m_playbackSubscribed = true;
    m_playbackPosition = state->playbackPosition().to_double();
    state->playbackPositionChanged().onReceive(this, [this](muse::audio::secs_t position) {
        m_playbackPosition = position.to_double();
        emit playbackPositionChanged();
    });

    //! NOTE: keep the score grid track in sync with the score's actual total play time
    //! (e.g. when measures are added/removed the score gets longer/shorter).
    const notation::IMasterNotationPtr master = globalContext()->currentMasterNotation();
    if (master && master->playback()) {
        master->playback()->totalPlayTimeChanged().onReceive(this, [this](muse::audio::secs_t) {
            emit scoreDurationChanged();
            updateScoreBeatGrid();
        });
    }
}

void AudioTrackSettingsModel::chooseFile()
{
    const std::vector<std::string> filter {
        muse::trc("project", "Audio files") + " (*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.aiff *.aif)"
    };

    const muse::io::path_t path = interactive()->selectOpeningFileSync(muse::trc("project", "Choose audio track"), "", filter);
    if (path.empty()) {
        return;
    }

    if (m_settings.clips.empty()) {
        AudioClipSettings clip;
        clip.filePath = path;
        m_settings.clips.push_back(clip);
    } else {
        m_settings.clips[0].filePath = path;
    }

    m_originalBpm = 0.0;
    emit measuredBpmChanged();
    updateWaveform();
    updateClipsList();
    apply();
    notifyAll();
}

void AudioTrackSettingsModel::replaceFile()
{
    const std::vector<std::string> filter {
        muse::trc("project", "Audio files") + " (*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.aiff *.aif)"
    };

    const muse::io::path_t path = interactive()->selectOpeningFileSync(muse::trc("project", "Replace audio"), "", filter);
    if (path.empty()) {
        return;
    }

    if (m_settings.clips.empty()) {
        AudioClipSettings clip;
        clip.filePath = path;
        m_settings.clips.push_back(clip);
    } else {
        m_settings.clips[0].filePath = path;
    }

    //! NOTE: keep the existing alignment/offset/fade settings; only swap the source file.
    m_duration = 0.0;
    m_waveformPeaks.clear();
    m_originalBpm = 0.0;
    emit measuredBpmChanged();
    updateWaveform();
    updateClipsList();
    apply();
    notifyAll();
}

void AudioTrackSettingsModel::apply()
{
    const IProjectAudioSettingsPtr settings = audioSettings();
    if (!settings) {
        return;
    }

    settings->setAudioTrackSettings(m_settings);
}

void AudioTrackSettingsModel::remove()
{
    m_settings = AudioTrackSettings();
    m_duration = 0.0;
    m_waveformPeaks.clear();
    m_originalBpm = 0.0;
    emit measuredBpmChanged();
    updateClipsList();
    apply();
    notifyAll();
}

void AudioTrackSettingsModel::seek(double seconds)
{
    commandDispatcher()->dispatch(muse::rcommand::Command("command://playback/rewind"),
                                  muse::rcommand::Params({ { "position", muse::Val(seconds) } }));
}

void AudioTrackSettingsModel::toggleMetronome()
{
    m_metronomeEnabled = !m_metronomeEnabled;
    playbackController()->toggleMetronome();
    emit metronomeEnabledChanged();
}

bool AudioTrackSettingsModel::metronomeEnabled() const
{
    return m_metronomeEnabled;
}

bool AudioTrackSettingsModel::scoreMuted() const
{
    return m_scoreMuted;
}

void AudioTrackSettingsModel::toggleScoreMute()
{
    m_scoreMuted = !m_scoreMuted;

    playback::IPlaybackController::SoloMuteState state;
    state.mute = m_scoreMuted;
    state.solo = false;

    const notation::IMasterNotationPtr master = globalContext()->currentMasterNotation();
    const notation::INotationPlaybackPtr notationPlayback = master ? master->playback() : nullptr;
    const engraving::InstrumentTrackId metronomeTrackId = notationPlayback ? notationPlayback->metronomeTrackId() : engraving::InstrumentTrackId();

    for (const auto& pair : playbackController()->instrumentTrackIdMap()) {
        if (pair.first == metronomeTrackId) {
            continue;   //! NOTE: never touch the metronome when muting the score
        }
        playbackController()->setTrackSoloMuteState(pair.first, state);
    }

    emit scoreMutedChanged();
}

double AudioTrackSettingsModel::masterVolumeDb() const
{
    return m_masterVolumeDb;
}

void AudioTrackSettingsModel::setMasterVolumeDb(double value)
{
    const IProjectAudioSettingsPtr settings = audioSettings();
    m_masterVolumeDb = value;
    if (settings) {
        AudioOutputParams params = settings->masterAudioOutputParams();
        params.volume = muse::audio::volume_db_t(value);
        playback()->setMasterControlParams(params.control());
    }
    emit masterVolumeDbChanged();
}

double AudioTrackSettingsModel::scoreVolumeDb() const
{
    return m_scoreVolumeDb;
}

void AudioTrackSettingsModel::setScoreVolumeDb(double value)
{
    m_scoreVolumeDb = value;

    const IProjectAudioSettingsPtr settings = audioSettings();
    if (settings) {
        for (const auto& pair : playbackController()->instrumentTrackIdMap()) {
            if (!settings->trackHasExistingOutputParams(pair.first)) {
                continue;
            }
            AudioOutputParams params = settings->trackOutputParams(pair.first);
            params.volume = muse::audio::volume_db_t(value);
            playback()->setControlParams(pair.second, params.control());
        }
    }

    emit scoreVolumeDbChanged();
}

double AudioTrackSettingsModel::snapToBeat(double seconds)
{
    const notation::IMasterNotationPtr master = globalContext()->currentMasterNotation();
    if (!master || !master->playback()) {
        return std::round(seconds * 10.0) / 10.0;
    }

    const notation::INotationPlaybackPtr playback = master->playback();
    const muse::midi::tick_t tick = playback->secToTick(muse::audio::secs_t(seconds));
    const engraving::MeasureBeat beat = playback->beat(tick);
    const muse::midi::tick_t beatTick = playback->beatToRawTick(beat.measureIndex, int(beat.beat));
    return playback->playedTickToSec(beatTick).to_double();
}

IProjectAudioSettingsPtr AudioTrackSettingsModel::audioSettings() const
{
    const project::INotationProjectPtr project = globalContext()->currentProject();
    return project ? project->audioSettings() : nullptr;
}

void AudioTrackSettingsModel::updateClipsList()
{
    m_clips.clear();
    for (const AudioClipSettings& clip : m_settings.clips) {
        QVariantMap map;
        map.insert("filePath", clip.filePath.toQString());
        map.insert("startOffset", clip.startOffset.to_double());
        map.insert("clipStart", clip.clipStart.to_double());
        map.insert("clipEnd", clip.clipEnd.to_double());
        map.insert("speed", clip.speed);
        map.insert("volume", clip.volume.to_double());
        map.insert("muted", clip.muted);
        map.insert("fadeIn", clip.fadeIn.to_double());
        map.insert("fadeOut", clip.fadeOut.to_double());
        m_clips.append(map);
    }
    emit clipsChanged();
}

const AudioClipSettings* AudioTrackSettingsModel::firstClip() const
{
    return m_settings.clips.empty() ? nullptr : &m_settings.clips[0];
}

void AudioTrackSettingsModel::updateWaveform()
{
    m_waveformPeaks.clear();
    m_duration = 0.0;
    emit waveformPeaksChanged();
    emit durationChanged();

    const AudioClipSettings* clip = firstClip();
    if (!clip || clip->filePath.empty()) {
        return;
    }

    const QString path = clip->filePath.toQString();

    //! NOTE: waveform peaks are computed off the UI thread so that importing a large
    //! audio file does not freeze the interface. The result is posted back to the UI thread.
    QPointer<AudioTrackSettingsModel> self(this);
    std::thread([self, path]() {
        double duration = 0.0;
        QVariantList peaks;
        bool ok = false;

        if (path.endsWith(".wav", Qt::CaseInsensitive) || path.endsWith(".aiff", Qt::CaseInsensitive)
            || path.endsWith(".aif", Qt::CaseInsensitive)) {
            ok = computeWavPeaks(path, duration, peaks);
        } else if (path.endsWith(".mp3", Qt::CaseInsensitive)) {
            ok = computeMp3Peaks(path, duration, peaks);
        } else if (path.endsWith(".flac", Qt::CaseInsensitive)) {
            ok = computeFlacPeaks(path, duration, peaks);
        }

        if (!ok || !self) {
            return;
        }

        QMetaObject::invokeMethod(self.data(), [self, duration, peaks]() {
            if (!self) {
                return;
            }
            self->m_duration = duration;
            self->m_waveformPeaks = peaks;
            emit self->durationChanged();
            emit self->waveformPeaksChanged();
        }, Qt::QueuedConnection);
    }).detach();
}

void AudioTrackSettingsModel::notifyAll()
{
    const bool nowHasTrack = m_settings.isValid();
    if (nowHasTrack != m_prevHasTrack) {
        m_prevHasTrack = nowHasTrack;
        emit hasTrackChanged();
    }

    emit filePathChanged();
    emit startOffsetChanged();
    emit clipStartChanged();
    emit clipEndChanged();
    emit volumeDbChanged();
    emit mutedChanged();
    emit tempoSyncChanged();
    emit speedChanged();
    emit durationChanged();
    emit waveformPeaksChanged();
    emit clipsChanged();
    emit scoreOffsetChanged();
    emit fadeInChanged();
    emit fadeOutChanged();
}

QString AudioTrackSettingsModel::filePath() const { const AudioClipSettings* c = firstClip(); return c ? c->filePath.toQString() : QString(); }
double AudioTrackSettingsModel::startOffset() const { const AudioClipSettings* c = firstClip(); return c ? c->startOffset.to_double() : 0.0; }
double AudioTrackSettingsModel::clipStart() const { const AudioClipSettings* c = firstClip(); return c ? c->clipStart.to_double() : 0.0; }
double AudioTrackSettingsModel::clipEnd() const { const AudioClipSettings* c = firstClip(); return c ? c->clipEnd.to_double() : 0.0; }
double AudioTrackSettingsModel::volumeDb() const { const AudioClipSettings* c = firstClip(); return c ? c->volume.to_double() : 0.0; }
bool AudioTrackSettingsModel::muted() const { const AudioClipSettings* c = firstClip(); return c ? c->muted : false; }
bool AudioTrackSettingsModel::tempoSync() const { return false; }
double AudioTrackSettingsModel::speed() const { const AudioClipSettings* c = firstClip(); return c ? c->speed : 1.0; }
bool AudioTrackSettingsModel::hasTrack() const { return m_settings.isValid(); }
double AudioTrackSettingsModel::duration() const
{
    //! NOTE: m_duration is the source file length; the audible/visible length is the
    //! source length divided by the current time-stretch speed.
    const AudioClipSettings* clip = firstClip();
    const double s = (clip && clip->speed > 0.01f) ? clip->speed : 1.0;
    return m_duration / s;
}
QVariantList AudioTrackSettingsModel::waveformPeaks() const { return m_waveformPeaks; }
double AudioTrackSettingsModel::playbackPosition() const { return m_playbackPosition; }
QVariantList AudioTrackSettingsModel::clips() const { return m_clips; }
double AudioTrackSettingsModel::measuredBpm() const
{
    const AudioClipSettings* clip = firstClip();
    const double speed = clip ? clip->speed : 1.0;
    return m_originalBpm * speed;
}
double AudioTrackSettingsModel::scoreOffset() const { return m_settings.scoreOffset.to_double(); }
double AudioTrackSettingsModel::scoreDuration() const
{
    const notation::IMasterNotationPtr master = globalContext()->currentMasterNotation();
    return (master && master->playback()) ? master->playback()->totalPlayTime().to_double() : 0.0;
}
double AudioTrackSettingsModel::fadeIn() const { const AudioClipSettings* c = firstClip(); return c ? c->fadeIn.to_double() : 0.0; }
double AudioTrackSettingsModel::fadeOut() const { const AudioClipSettings* c = firstClip(); return c ? c->fadeOut.to_double() : 0.0; }
QVariantList AudioTrackSettingsModel::scoreBeatGrid() const { return m_scoreBeatGrid; }

void AudioTrackSettingsModel::updateScoreBeatGrid()
{
    m_scoreBeatGrid.clear();

    //! 【固定不变式 · 永不可改】
    //! 乐谱轨竖线 = 每个小节的第一拍，且必须与播放头始终同步。
    //! 时间换算顺序固定为：原始 tick -> playPositionTickByRawTick(展开重复) -> playedTickToSec(含速度)。
    //! 任何后续改动都不得改变这个换算逻辑。

    const notation::IMasterNotationPtr master = globalContext()->currentMasterNotation();
    if (!master || !master->playback()) {
        emit scoreBeatGridChanged();
        return;
    }

    const notation::INotationPlaybackPtr playback = master->playback();
    const muse::audio::secs_t total = playback->totalPlayTime();
    if (total <= muse::audio::secs_t(0.0)) {
        emit scoreBeatGridChanged();
        return;
    }

    const muse::midi::tick_t lastTick = playback->secToTick(total);
    const engraving::MeasureBeat lastBeat = playback->beat(lastTick);
    const int measureCount = lastBeat.maxMeasureIndex + 1;
    if (measureCount <= 0 || measureCount > 100000) {
        emit scoreBeatGridChanged();
        return;
    }

    //! NOTE: one vertical line per beat; the first beat of each measure (downbeat) is
    //! drawn thicker in the UI. Supports any time signature (4/4, 3/4, 6/8, ...).
    for (int m = 0; m < measureCount; ++m) {
        const muse::midi::tick_t measureTick = playback->beatToRawTick(m, 0);
        const engraving::MeasureBeat mb = playback->beat(measureTick);
        const int beats = std::max(1, mb.maxBeatIndex + 1);
        for (int b = 0; b < beats; ++b) {
            const muse::midi::tick_t rawTick = playback->beatToRawTick(m, b);
            const muse::RetVal<muse::midi::tick_t> playedTick = playback->playPositionTickByRawTick(rawTick);
            const double time = playback->playedTickToSec(playedTick.val).to_double();
            QVariantMap item;
            item.insert("time", time);
            item.insert("isDownbeat", b == 0);
            m_scoreBeatGrid.append(item);
        }
    }

    emit scoreBeatGridChanged();
}

void AudioTrackSettingsModel::setStartOffset(double value) { if (!m_settings.clips.empty()) { m_settings.clips[0].startOffset = muse::secs_t(value); } emit startOffsetChanged(); updateClipsList(); }
void AudioTrackSettingsModel::setClipStart(double value) { if (!m_settings.clips.empty()) { m_settings.clips[0].clipStart = muse::secs_t(value); } emit clipStartChanged(); updateClipsList(); }
void AudioTrackSettingsModel::setClipEnd(double value) { if (!m_settings.clips.empty()) { m_settings.clips[0].clipEnd = muse::secs_t(value); } emit clipEndChanged(); updateClipsList(); }
void AudioTrackSettingsModel::setVolumeDb(double value) { if (!m_settings.clips.empty()) { m_settings.clips[0].volume = muse::audio::volume_db_t(value); } emit volumeDbChanged(); updateClipsList(); }
void AudioTrackSettingsModel::setMuted(bool value) { if (!m_settings.clips.empty()) { m_settings.clips[0].muted = value; } emit mutedChanged(); updateClipsList(); }
void AudioTrackSettingsModel::setTempoSync(bool value) { emit tempoSyncChanged(); }
void AudioTrackSettingsModel::setSpeed(double value) { if (!m_settings.clips.empty()) { m_settings.clips[0].speed = float(value); } emit speedChanged(); updateClipsList(); }

void AudioTrackSettingsModel::addClipFromFile()
{
    const std::vector<std::string> filter {
        muse::trc("project", "Audio files") + " (*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.aiff *.aif)"
    };
    const muse::io::path_t path = interactive()->selectOpeningFileSync(muse::trc("project", "Choose audio track"), "", filter);
    if (path.empty()) {
        return;
    }

    AudioClipSettings clip;
    clip.filePath = path;
    m_settings.clips.push_back(clip);
    updateWaveform();
    updateClipsList();
    apply();
    notifyAll();
}

void AudioTrackSettingsModel::splitClip(int index, double at)
{
    if (index < 0 || index >= int(m_settings.clips.size())) {
        return;
    }

    AudioClipSettings& clip = m_settings.clips[index];
    const double dur = m_duration > 0.0 ? m_duration : 600.0;
    const double splitSource = clip.clipStart + (at - clip.startOffset);
    if (splitSource <= clip.clipStart || (clip.clipEnd > 0.0 && splitSource >= clip.clipEnd) || splitSource >= dur) {
        return;
    }

    AudioClipSettings right = clip;
    right.clipStart = muse::secs_t(splitSource);
    right.startOffset = muse::secs_t(at);
    clip.clipEnd = muse::secs_t(splitSource);

    m_settings.clips.insert(m_settings.clips.begin() + index + 1, right);
    updateClipsList();
    apply();
    notifyAll();
}

void AudioTrackSettingsModel::removeClip(int index)
{
    if (index < 0 || index >= int(m_settings.clips.size())) {
        return;
    }
    m_settings.clips.erase(m_settings.clips.begin() + index);
    updateClipsList();
    apply();
    notifyAll();
}

void AudioTrackSettingsModel::moveClip(int index, double startOffset)
{
    if (index < 0 || index >= int(m_settings.clips.size())) {
        return;
    }
    m_settings.clips[index].startOffset = muse::secs_t(startOffset);
    updateClipsList();
    apply();
    if (index == 0) {
        emit startOffsetChanged();
    }
}

void AudioTrackSettingsModel::trimClip(int index, double clipStart, double clipEnd)
{
    if (index < 0 || index >= int(m_settings.clips.size())) {
        return;
    }
    m_settings.clips[index].clipStart = muse::secs_t(clipStart);
    m_settings.clips[index].clipEnd = muse::secs_t(clipEnd);
    updateClipsList();
    apply();
}

void AudioTrackSettingsModel::setClipSpeed(int index, double speed)
{
    if (index < 0 || index >= int(m_settings.clips.size())) {
        return;
    }
    m_settings.clips[index].speed = float(speed);
    updateClipsList();
    apply();
}

void AudioTrackSettingsModel::setClipVolume(int index, double volume)
{
    if (index < 0 || index >= int(m_settings.clips.size())) {
        return;
    }
    m_settings.clips[index].volume = muse::audio::volume_db_t(volume);
    updateClipsList();
    apply();
}

void AudioTrackSettingsModel::setClipMuted(int index, bool muted)
{
    if (index < 0 || index >= int(m_settings.clips.size())) {
        return;
    }
    m_settings.clips[index].muted = muted;
    updateClipsList();
    apply();
}

void AudioTrackSettingsModel::setClipFade(int index, double fadeIn, double fadeOut)
{
    if (index < 0 || index >= int(m_settings.clips.size())) {
        return;
    }
    m_settings.clips[index].fadeIn = muse::secs_t(fadeIn);
    m_settings.clips[index].fadeOut = muse::secs_t(fadeOut);
    updateClipsList();
    apply();
}

void AudioTrackSettingsModel::tapTempo()
{
    const AudioClipSettings* clip = firstClip();
    if (!clip || clip->filePath.empty()) {
        return;
    }

    std::vector<float> mono;
    unsigned int sampleRate = 0;
    const QString path = clip->filePath.toQString();

    if (path.endsWith(".mp3", Qt::CaseInsensitive)) {
        if (!decodeMp3Mono(path, mono, sampleRate)) {
            return;
        }
    } else if (path.endsWith(".flac", Qt::CaseInsensitive)) {
        if (!decodeFlacMono(path, mono, sampleRate)) {
            return;
        }
    } else {
        if (!decodeWavMono(path, mono, sampleRate)) {
            return;
        }
    }

    double bpm = detectBpm(mono, sampleRate);
    if (bpm <= 0.0) {
        return;
    }

    bpm = std::round(bpm * 100.0) / 100.0;
    m_originalBpm = bpm;
    emit measuredBpmChanged();
}

void AudioTrackSettingsModel::setBpm(double bpm)
{
    if (m_settings.clips.empty() || !std::isfinite(bpm) || bpm <= 0.0
        || !std::isfinite(m_originalBpm) || m_originalBpm <= 0.0) {
        return;
    }

    const double speed = std::clamp(bpm / m_originalBpm, 0.25, 4.0);
    m_settings.clips[0].speed = float(speed);
    updateClipsList();
    apply();
    emit speedChanged();
    emit measuredBpmChanged();
}

void AudioTrackSettingsModel::resetSpeed()
{
    if (m_settings.clips.empty()) {
        return;
    }

    m_settings.clips[0].speed = 1.0f;
    updateClipsList();
    apply();
    emit speedChanged();
    emit measuredBpmChanged();
}

void AudioTrackSettingsModel::setScoreOffset(double offset)
{
    m_settings.scoreOffset = muse::secs_t(offset);
    emit scoreOffsetChanged();
}
void AudioTrackSettingsModel::setFadeIn(double value)
{
    if (!m_settings.clips.empty()) {
        m_settings.clips[0].fadeIn = muse::secs_t(value);
    }
    emit fadeInChanged();
    updateClipsList();
}
void AudioTrackSettingsModel::setFadeOut(double value)
{
    if (!m_settings.clips.empty()) {
        m_settings.clips[0].fadeOut = muse::secs_t(value);
    }
    emit fadeOutChanged();
    updateClipsList();
}
