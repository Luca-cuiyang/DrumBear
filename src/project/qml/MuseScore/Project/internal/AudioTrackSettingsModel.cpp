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
#include <cmath>
#include <vector>

#include <QFile>
#include <QFileInfo>

#include "log.h"
#include "project/inotationproject.h"

#include "audio/engine/internal/codecs/thirdparty/dr_mp3.h"

using namespace mu::project;

namespace {
bool computeWavPeaks(const QString& path, double& duration, QVariantList& peaks, int buckets = 600)
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
        float peak = 0.f;
        for (int f = startFrame; f < endFrame; ++f) {
            const int sampleIndex = f * channels * bytesPerSample;
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
            } else {
                continue;
            }
            peak = std::max(peak, std::abs(value));
        }
        peaks.append(peak);
    }

    return true;
}

bool computeMp3Peaks(const QString& path, double& duration, QVariantList& peaks, int buckets = 600)
{
    drmp3 mp3;
    if (!drmp3_init_file(&mp3, path.toUtf8().constData(), nullptr)) {
        return false;
    }

    const uint64_t totalFrames = drmp3_get_pcm_frame_count(&mp3);
    if (totalFrames == 0 || mp3.channels == 0 || mp3.sampleRate == 0) {
        drmp3_uninit(&mp3);
        return false;
    }

    std::vector<float> samples(totalFrames * mp3.channels);
    const uint64_t read = drmp3_read_pcm_frames_f32(&mp3, totalFrames, samples.data());
    drmp3_uninit(&mp3);

    if (read != totalFrames) {
        return false;
    }

    duration = double(totalFrames) / mp3.sampleRate;
    const int bucketCount = std::min(buckets, int(totalFrames));
    peaks.clear();
    peaks.reserve(bucketCount);

    for (int b = 0; b < bucketCount; ++b) {
        const int startFrame = int((uint64_t(b) * totalFrames) / bucketCount);
        const int endFrame = int((uint64_t(b + 1) * totalFrames) / bucketCount);
        float peak = 0.f;
        for (int f = startFrame; f < endFrame; ++f) {
            for (unsigned int c = 0; c < mp3.channels; ++c) {
                const size_t index = size_t(f) * mp3.channels + c;
                if (index < samples.size()) {
                    peak = std::max(peak, std::abs(samples[index]));
                }
            }
        }
        peaks.append(peak);
    }

    return true;
}
}

AudioTrackSettingsModel::AudioTrackSettingsModel(QObject* parent)
    : QObject(parent), muse::Contextable(muse::iocCtxForQmlObject(this))
{
}

void AudioTrackSettingsModel::load()
{
    const IProjectAudioSettingsPtr settings = audioSettings();
    if (!settings) {
        return;
    }

    m_settings = settings->audioTrackSettings();
    m_duration = 0.0;
    updateWaveform();
    notifyAll();
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

    m_settings.filePath = path;
    m_duration = 0.0;
    updateWaveform();
    emit filePathChanged();
    emit hasTrackChanged();
    emit durationChanged();
    emit waveformPeaksChanged();
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
    apply();
    notifyAll();
}

IProjectAudioSettingsPtr AudioTrackSettingsModel::audioSettings() const
{
    const project::INotationProjectPtr project = globalContext()->currentProject();
    return project ? project->audioSettings() : nullptr;
}

void AudioTrackSettingsModel::updateWaveform()
{
    m_waveformPeaks.clear();
    m_duration = 0.0;

    if (m_settings.filePath.empty()) {
        return;
    }

    double duration = 0.0;
    QVariantList peaks;
    const QString path = m_settings.filePath.toQString();
    if (path.endsWith(".wav", Qt::CaseInsensitive) || path.endsWith(".aiff", Qt::CaseInsensitive)
        || path.endsWith(".aif", Qt::CaseInsensitive)) {
        if (!computeWavPeaks(path, duration, peaks)) {
            peaks.clear();
        }
    } else if (path.endsWith(".mp3", Qt::CaseInsensitive)) {
        if (!computeMp3Peaks(path, duration, peaks)) {
            peaks.clear();
        }
    }

    if (!peaks.isEmpty()) {
        m_duration = duration;
        m_waveformPeaks = peaks;
    }
}

void AudioTrackSettingsModel::notifyAll()
{
    emit filePathChanged();
    emit startOffsetChanged();
    emit clipStartChanged();
    emit clipEndChanged();
    emit volumeDbChanged();
    emit mutedChanged();
    emit tempoSyncChanged();
    emit hasTrackChanged();
    emit durationChanged();
    emit waveformPeaksChanged();
}

QString AudioTrackSettingsModel::filePath() const { return m_settings.filePath.toQString(); }
double AudioTrackSettingsModel::startOffset() const { return m_settings.startOffset.to_double(); }
double AudioTrackSettingsModel::clipStart() const { return m_settings.clipStart.to_double(); }
double AudioTrackSettingsModel::clipEnd() const { return m_settings.clipEnd.to_double(); }
double AudioTrackSettingsModel::volumeDb() const { return m_settings.volume.to_double(); }
bool AudioTrackSettingsModel::muted() const { return m_settings.muted; }
bool AudioTrackSettingsModel::tempoSync() const { return m_settings.tempoSync; }
bool AudioTrackSettingsModel::hasTrack() const { return m_settings.isValid(); }
double AudioTrackSettingsModel::duration() const { return m_duration; }
QVariantList AudioTrackSettingsModel::waveformPeaks() const { return m_waveformPeaks; }

void AudioTrackSettingsModel::setStartOffset(double value) { m_settings.startOffset = muse::secs_t(value); emit startOffsetChanged(); }
void AudioTrackSettingsModel::setClipStart(double value) { m_settings.clipStart = muse::secs_t(value); emit clipStartChanged(); }
void AudioTrackSettingsModel::setClipEnd(double value) { m_settings.clipEnd = muse::secs_t(value); emit clipEndChanged(); }
void AudioTrackSettingsModel::setVolumeDb(double value) { m_settings.volume = muse::audio::volume_db_t(value); emit volumeDbChanged(); }
void AudioTrackSettingsModel::setMuted(bool value) { m_settings.muted = value; emit mutedChanged(); }
void AudioTrackSettingsModel::setTempoSync(bool value) { m_settings.tempoSync = value; emit tempoSyncChanged(); }
