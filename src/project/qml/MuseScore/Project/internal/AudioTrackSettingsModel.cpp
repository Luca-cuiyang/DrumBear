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
#include "notation/imasternotation.h"
#include "notation/inotationplayback.h"
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

    const uint64_t frames = drmp3_get_pcm_frame_count(&mp3);
    if (frames == 0 || mp3.channels == 0 || mp3.sampleRate == 0) {
        drmp3_uninit(&mp3);
        return false;
    }

    std::vector<float> interleaved(frames * mp3.channels);
    const uint64_t read = drmp3_read_pcm_frames_f32(&mp3, frames, interleaved.data());
    sampleRate = mp3.sampleRate;
    drmp3_uninit(&mp3);

    if (read != frames) {
        return false;
    }

    mono.resize(frames);
    for (uint64_t f = 0; f < frames; ++f) {
        float acc = 0.f;
        for (unsigned int c = 0; c < mp3.channels; ++c) {
            acc += interleaved[f * mp3.channels + c];
        }
        mono[f] = acc / mp3.channels;
    }
    return true;
}

double detectBpm(const std::vector<float>& mono, unsigned int sampleRate)
{
    if (mono.empty() || sampleRate == 0) {
        return 0.0;
    }

    const unsigned int hop = std::max<unsigned int>(1, sampleRate / 50);
    std::vector<float> env;
    env.reserve(mono.size() / hop + 1);
    for (size_t i = 0; i + hop <= mono.size(); i += hop) {
        float e = 0.f;
        for (size_t j = i; j < i + hop; ++j) {
            e += mono[j] * mono[j];
        }
        env.push_back(std::sqrt(e / hop));
    }

    if (env.size() < 16) {
        return 0.0;
    }

    std::vector<float> onset(env.size(), 0.f);
    for (size_t i = 1; i < env.size(); ++i) {
        onset[i] = std::max(0.f, env[i] - env[i - 1]);
    }

    const int minLag = std::max(1, int(50 * 60 / 200));  // 200 BPM
    const int maxLag = std::min<int>(int(onset.size() - 1), int(50 * 60 / 60)); // 60 BPM
    double bestBpm = 120.0;
    double bestScore = -1.0;

    for (int lag = minLag; lag <= maxLag; ++lag) {
        double corr = 0.0;
        int n = 0;
        for (int i = 0; i + lag < int(onset.size()); ++i) {
            corr += double(onset[i]) * double(onset[i + lag]);
            ++n;
        }
        if (n == 0) {
            continue;
        }
        corr /= n;
        if (corr > bestScore) {
            bestScore = corr;
            bestBpm = 60.0 * 50.0 / lag;
        }
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

    m_settings = settings->audioTrackSettings();
    m_duration = 0.0;
    updateWaveform();
    notifyAll();
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

    updateWaveform();
    updateClipsList();
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
    updateClipsList();
    apply();
    notifyAll();
}

void AudioTrackSettingsModel::seek(double seconds)
{
    commandDispatcher()->dispatch(muse::rcommand::Command("command://playback/rewind"),
                                  muse::rcommand::Params({ { "position", muse::Val(seconds) } }));
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

    const AudioClipSettings* clip = firstClip();
    if (!clip || clip->filePath.empty()) {
        return;
    }

    double duration = 0.0;
    QVariantList peaks;
    const QString path = clip->filePath.toQString();
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
    emit speedChanged();
    emit hasTrackChanged();
    emit durationChanged();
    emit waveformPeaksChanged();
    emit clipsChanged();
    emit scoreOffsetChanged();
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
double AudioTrackSettingsModel::duration() const { return m_duration; }
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
    } else {
        if (!decodeWavMono(path, mono, sampleRate)) {
            return;
        }
    }

    const double bpm = detectBpm(mono, sampleRate);
    if (bpm <= 0.0) {
        return;
    }

    m_originalBpm = bpm;
    emit measuredBpmChanged();
}

void AudioTrackSettingsModel::setBpm(double bpm)
{
    if (m_settings.clips.empty() || bpm <= 0.0 || m_originalBpm <= 0.0) {
        return;
    }

    m_settings.clips[0].speed = float(bpm / m_originalBpm);
    updateClipsList();
    apply();
    emit speedChanged();
    emit measuredBpmChanged();
}

void AudioTrackSettingsModel::setScoreOffset(double offset)
{
    m_settings.scoreOffset = muse::secs_t(offset);
    apply();
    emit scoreOffsetChanged();
}
