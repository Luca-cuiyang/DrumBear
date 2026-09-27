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
#include <qqmlintegration.h>

#include "context/iglobalcontext.h"
#include "interactive/iinteractive.h"
#include "modularity/ioc.h"

#include "project/iprojectaudiosettings.h"

namespace mu::project {
class AudioTrackSettingsModel : public QObject, public muse::Contextable
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

    void setStartOffset(double value);
    void setClipStart(double value);
    void setClipEnd(double value);
    void setVolumeDb(double value);
    void setMuted(bool value);
    void setTempoSync(bool value);
    void setSpeed(double value);

    Q_INVOKABLE void load();
    Q_INVOKABLE void chooseFile();
    Q_INVOKABLE void apply();
    Q_INVOKABLE void remove();

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

private:
    IProjectAudioSettingsPtr audioSettings() const;
    void updateWaveform();
    void notifyAll();

    muse::ContextInject<context::IGlobalContext> globalContext = { this };
    muse::ContextInject<muse::IInteractive> interactive = { this };

    AudioTrackSettings m_settings;
    double m_duration = 0.0;
    QVariantList m_waveformPeaks;
};
}

#endif // DBSCORE_AUDIOTRACKSETTINGSMODEL_H
