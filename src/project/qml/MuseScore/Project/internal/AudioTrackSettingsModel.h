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
#include "async/asyncable.h"

#include "project/iprojectaudiosettings.h"
#include "playback/iplaybackcontroller.h"
#include "notation/inotationconfiguration.h"
#include "audio/main/iplayback.h"
#include "cloud/dbscoreauthorization/idbscoreauthorizationservice.h"

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
    Q_PROPERTY(bool hasTrack READ hasTrack NOTIFY hasTrackChanged)
    Q_PROPERTY(double duration READ duration NOTIFY durationChanged)
    Q_PROPERTY(QVariantList waveformPeaks READ waveformPeaks NOTIFY waveformPeaksChanged)
    Q_PROPERTY(double playbackPosition READ playbackPosition NOTIFY playbackPositionChanged)
    Q_PROPERTY(double measuredBpm READ measuredBpm NOTIFY measuredBpmChanged)
    Q_PROPERTY(double scoreOffset READ scoreOffset WRITE setScoreOffset NOTIFY scoreOffsetChanged)
    Q_PROPERTY(double scoreDuration READ scoreDuration NOTIFY scoreDurationChanged)
    Q_PROPERTY(QVariantList scoreBeatGrid READ scoreBeatGrid NOTIFY scoreBeatGridChanged)
    Q_PROPERTY(bool scoreMuted READ scoreMuted NOTIFY scoreMutedChanged)
    Q_PROPERTY(bool metronomeEnabled READ metronomeEnabled NOTIFY metronomeEnabledChanged)
    Q_PROPERTY(double masterVolumeDb READ masterVolumeDb WRITE setMasterVolumeDb NOTIFY masterVolumeDbChanged)
    Q_PROPERTY(double scoreVolumeDb READ scoreVolumeDb WRITE setScoreVolumeDb NOTIFY scoreVolumeDbChanged)
    Q_PROPERTY(bool hasProAccess READ hasProAccess NOTIFY proAccessChanged)

public:
    explicit AudioTrackSettingsModel(QObject* parent = nullptr);

    QString filePath() const;
    double startOffset() const;
    double clipStart() const;
    double clipEnd() const;
    double volumeDb() const;
    bool muted() const;
    bool hasTrack() const;
    double duration() const;
    QVariantList waveformPeaks() const;
    double playbackPosition() const;
    double measuredBpm() const;
    double scoreOffset() const;
    double scoreDuration() const;
    QVariantList scoreBeatGrid() const;
    bool scoreMuted() const;
    bool metronomeEnabled() const;
    double masterVolumeDb() const;
    double scoreVolumeDb() const;
    bool hasProAccess() const;

    Q_INVOKABLE void setStartOffset(double value);
    Q_INVOKABLE void setClipStart(double value);
    Q_INVOKABLE void setClipEnd(double value);
    Q_INVOKABLE void setVolumeDb(double value);
    Q_INVOKABLE void setMuted(bool value);

    Q_INVOKABLE void load();
    Q_INVOKABLE void chooseFile();
    Q_INVOKABLE void replaceFile();
    Q_INVOKABLE void apply();
    Q_INVOKABLE void remove();
    Q_INVOKABLE void seek(double seconds);
    Q_INVOKABLE void tapTempo();
    Q_INVOKABLE void setScoreOffset(double offset);
    Q_INVOKABLE void setPanelVisible(bool visible);
    Q_INVOKABLE void toggleMetronome();
    Q_INVOKABLE void toggleScoreMute();
    Q_INVOKABLE void setMasterVolumeDb(double value);
    Q_INVOKABLE void setScoreVolumeDb(double value);

signals:
    void filePathChanged();
    void startOffsetChanged();
    void clipStartChanged();
    void clipEndChanged();
    void volumeDbChanged();
    void mutedChanged();
    void hasTrackChanged();
    void durationChanged();
    void waveformPeaksChanged();
    void playbackPositionChanged();
    void measuredBpmChanged();
    void scoreOffsetChanged();
    void scoreDurationChanged();
    void scoreBeatGridChanged();
    void scoreMutedChanged();
    void metronomeEnabledChanged();
    void masterVolumeDbChanged();
    void scoreVolumeDbChanged();
    void proAccessChanged();

private:
    IProjectAudioSettingsPtr audioSettings() const;
    void updateWaveform();
    void subscribeOnPlayback();
    void updateScoreBeatGrid();
    const AudioClipSettings* firstClip() const;
    void notifyAll();
    bool ensureProAccess();

    muse::ContextInject<context::IGlobalContext> globalContext = { this };
    muse::ContextInject<muse::IInteractive> interactive = { this };
    muse::ContextInject<muse::rcommand::ICommandDispatcher> commandDispatcher = { this };
    muse::ContextInject<playback::IPlaybackController> playbackController = { this };
    muse::ContextInject<muse::audio::IPlayback> playback = { this };
    muse::GlobalInject<notation::INotationConfiguration> notationConfiguration;
    muse::GlobalInject<muse::cloud::IDbScoreAuthorizationService> authorization;

    AudioTrackSettings m_settings;
    double m_duration = 0.0;
    QVariantList m_waveformPeaks;
    double m_playbackPosition = 0.0;
    bool m_settingsSubscribed = false;
    bool m_playbackSubscribed = false;
    bool m_projectSubscribed = false;
    bool m_panelVisible = false;
    double m_originalBpm = 0.0;
    QVariantList m_scoreBeatGrid;
    bool m_scoreMuted = false;
    bool m_metronomeEnabled = false;
    double m_scoreVolumeDb = 0.0;
    double m_masterVolumeDb = 0.0;
    bool m_volumeInitialized = false;
    bool m_prevHasTrack = false;
};
}

#endif // DBSCORE_AUDIOTRACKSETTINGSMODEL_H
