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
#ifndef DBSCORE_AUDIOTRACKSETTINGSMODEL_H
#define DBSCORE_AUDIOTRACKSETTINGSMODEL_H

#include <QObject>
#include <QVariantList>
#include <QElapsedTimer>
#include <qqmlintegration.h>

#include "context/iglobalcontext.h"
#include "interactive/iinteractive.h"
#include "modularity/ioc.h"
#include "rcommand/icommanddispatcher.h"

#include "project/iprojectaudiosettings.h"

namespace mu::project {
class AudioTrackSettingsModel : public QObject, public muse::Contextable, public muse::async::Asyncable
{
    Q_OBJECT
    QML_ELEMENT

    Q_PROPERTY(QString filePath READ filePath NOTIFY filePathChanged)
    Q_PROPERTY(double startOffset READ startOffset WRITE setStartOffset NOTIFY startOffsetChanged)
    Q_PROPERTY(double clipStart READ clipStart WRITE setClipStart NOTIFY clipStartChanged)
    Q_PROPERTY(double clipEnd READ clipEnd WRITE setClipEnd NOTIFY clipEndChanged)
    Q_PROPERTY(double volumeDb READ volumeDb WRITE setVolumeDb NOTIFY volumeDbChanged)
    Q_PROPERTY(bool muted READ muted WRITE setMuted NOTIFY mutedChanged)
    Q_PROPERTY(bool tempoSync READ tempoSync WRITE setTempoSync NOTIFY tempoSyncChanged)
    Q_PROPERTY(double speed READ speed WRITE setSpeed NOTIFY speedChanged)
    Q_PROPERTY(bool hasTrack READ hasTrack NOTIFY hasTrackChanged)
    Q_PROPERTY(double duration READ duration NOTIFY durationChanged)
    Q_PROPERTY(QVariantList waveformPeaks READ waveformPeaks NOTIFY waveformPeaksChanged)
    Q_PROPERTY(double playbackPosition READ playbackPosition NOTIFY playbackPositionChanged)
    Q_PROPERTY(QVariantList clips READ clips NOTIFY clipsChanged)
    Q_PROPERTY(double measuredBpm READ measuredBpm NOTIFY measuredBpmChanged)
    Q_PROPERTY(double scoreOffset READ scoreOffset WRITE setScoreOffset NOTIFY scoreOffsetChanged)
    Q_PROPERTY(double scoreDuration READ scoreDuration NOTIFY scoreDurationChanged)

public:
    explicit AudioTrackSettingsModel(QObject* parent = nullptr);

    QString filePath() const;
    double startOffset() const;
    double clipStart() const;
    double clipEnd() const;
    double volumeDb() const;
    bool muted() const;
    bool tempoSync() const;
    double speed() const;
    bool hasTrack() const;
    double duration() const;
    QVariantList waveformPeaks() const;
    double playbackPosition() const;
    QVariantList clips() const;
    double measuredBpm() const;
    double scoreOffset() const;
    double scoreDuration() const;

    Q_INVOKABLE void setStartOffset(double value);
    Q_INVOKABLE void setClipStart(double value);
    Q_INVOKABLE void setClipEnd(double value);
    Q_INVOKABLE void setVolumeDb(double value);
    Q_INVOKABLE void setMuted(bool value);
    Q_INVOKABLE void setTempoSync(bool value);
    Q_INVOKABLE void setSpeed(double value);

    Q_INVOKABLE void load();
    Q_INVOKABLE void chooseFile();
    Q_INVOKABLE void apply();
    Q_INVOKABLE void remove();
    Q_INVOKABLE void seek(double seconds);
    Q_INVOKABLE double snapToBeat(double seconds);
    Q_INVOKABLE void addClipFromFile();
    Q_INVOKABLE void splitClip(int index, double at);
    Q_INVOKABLE void removeClip(int index);
    Q_INVOKABLE void moveClip(int index, double startOffset);
    Q_INVOKABLE void trimClip(int index, double clipStart, double clipEnd);
    Q_INVOKABLE void setClipSpeed(int index, double speed);
    Q_INVOKABLE void setClipVolume(int index, double volume);
    Q_INVOKABLE void setClipMuted(int index, bool muted);
    Q_INVOKABLE void setClipFade(int index, double fadeIn, double fadeOut);
    Q_INVOKABLE void tapTempo();
    Q_INVOKABLE void setBpm(double bpm);
    Q_INVOKABLE void setScoreOffset(double offset);

signals:
    void filePathChanged();
    void startOffsetChanged();
    void clipStartChanged();
    void clipEndChanged();
    void volumeDbChanged();
    void mutedChanged();
    void tempoSyncChanged();
    void speedChanged();
    void hasTrackChanged();
    void durationChanged();
    void waveformPeaksChanged();
    void playbackPositionChanged();
    void clipsChanged();
    void measuredBpmChanged();
    void scoreOffsetChanged();
    void scoreDurationChanged();

private:
    IProjectAudioSettingsPtr audioSettings() const;
    void updateWaveform();
    void subscribeOnPlayback();
    void updateClipsList();
    const AudioClipSettings* firstClip() const;
    void notifyAll();

    muse::ContextInject<context::IGlobalContext> globalContext = { this };
    muse::ContextInject<muse::IInteractive> interactive = { this };
    muse::ContextInject<muse::rcommand::ICommandDispatcher> commandDispatcher = { this };

    AudioTrackSettings m_settings;
    double m_duration = 0.0;
    QVariantList m_waveformPeaks;
    double m_playbackPosition = 0.0;
    bool m_settingsSubscribed = false;
    bool m_playbackSubscribed = false;
    QVariantList m_clips;
    double m_measuredBpm = 0.0;
    double m_originalBpm = 0.0;
    QElapsedTimer m_tapTimer;
    QList<qint64> m_tapTimes;
};
}

#endif // DBSCORE_AUDIOTRACKSETTINGSMODEL_H
