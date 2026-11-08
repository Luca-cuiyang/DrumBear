/*
 * SPDX-License-Identifier: GPL-3.0-only
 * MuseScore-Studio-CLA-applies
 *
 * MuseScore Studio
 * Music Composition & Notation
 *
 * Copyright (C) 2021 MuseScore Limited and others
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
#include "playbacktoolbarmodel.h"

#include <QCoreApplication>

#include <vector>

#include "global/containers.h"
#include "types/translatablestring.h"

#include "ui/view/musicalsymbolcodes.h"
#include "playback/playbacktypes.h"
#include "playback/playbackcommands.h"

#include "async/notifylist.h"
#include "engraving/dom/instrument.h"
#include "engraving/dom/measure.h"
#include "engraving/dom/score.h"
#include "notation/imasternotation.h"
#include "notation/inotation.h"
#include "notation/inotationelements.h"
#include "notation/inotationplayback.h"
#include "notation/inotationparts.h"
#include "project/inotationproject.h"
#include "project/iprojectaudiosettings.h"

#include "ui/toolconfig.h"

using namespace mu::playback;
using namespace mu::engraving;
using namespace muse;
using namespace muse::actions;
using namespace muse::ui;
using namespace muse::uicomponents;
using namespace muse::audio;

static const QString PLAY_TOGGLE_ID("play-toggle");
static const QString DRUMS_MUTE_ID("drums-mute");
static const QString ACCOMPANIMENT_MUTE_ID("accompaniment-mute");

static bool isStudioPlayerMode()
{
    return QCoreApplication::arguments().contains("--db-product-mode=studio-player");
}

static const ToolConfig& defaultPlaybackToolConfig()
{
    static ToolConfig config;
    if (!config.isValid()) {
        config.items = {
            { REWIND_COMMAND, true },
            { "play-toggle", true }, // virtual code
            { LOOP_TOGGLE_COMMAND, true },
            { LOOP_IN_COMMAND, true },
            { LOOP_OUT_COMMAND, true },
            { METRONOME_TOGGLE_COMMAND, true },
            { "drums-mute", true }, // virtual code
            { "accompaniment-mute", true }, // virtual code
        };
    }
    return config;
}

PlaybackToolBarModel::PlaybackToolBarModel(QObject* parent)
    : AbstractMenuModel(parent)
{
}

void PlaybackToolBarModel::load()
{
    AbstractMenuModel::load();
    updateActions();

    connect(this, &PlaybackToolBarModel::isToolbarFloatingChanged, this, &PlaybackToolBarModel::updateActions);

    setupConnections();
}

void PlaybackToolBarModel::setupConnections()
{
    playbackController()->isPlayAllowedChanged().onReceive(this, [this](bool) {
        emit isPlayAllowedChanged();
    });

    globalContext()->playbackState()->playbackStatusChanged().onReceive(this, [this](audio::PlaybackStatus) {
        updatePlayItem();
    });

    globalContext()->playbackState()->playbackPositionChanged().onReceive(this, [this](secs_t secs) {
        updatePlayPosition(secs);
    });

    playbackController()->totalPlayTimeChanged().onNotify(this, [this]() {
        emit maxPlayTimeChanged();
        secs_t pos = globalContext()->playbackState()->playbackPosition();
        updatePlayPosition(pos);
    });

    playbackController()->currentTempoChanged().onNotify(this, [this]() {
        emit tempoChanged();
    });
}

void PlaybackToolBarModel::updateActions()
{
    const bool studioPlayerMode = isStudioPlayerMode();
    MenuItemList result;
    MenuItemList settingsItems = {
        makeMenuItem(MIDI_TOGGLE_COMMAND),
        makeInputPitchMenu(),
        makeSeparator(),
        makeMenuItem(REPEATS_TOGGLE_COMMAND),
        makeMenuItem(CHORDSYMBOLS_TOGGLE_COMMAND),
        makeMenuItem(HEAR_PLAYBACK_WHEN_EDITING_TOGGLE_COMMAND),
        makeMenuItem(PAN_TOGGLE_COMMAND),
        makeMenuItem(COUNTIN_TOGGLE_COMMAND),
    };

    if (!m_isToolbarFloating) {
        settingsItems << makeSeparator();
    }

    //! NOTE At the moment no customization ability
    ToolConfig config = defaultPlaybackToolConfig();
    for (const ToolConfig::Item& item : config.items) {
        if (item.intent == PLAY_TOGGLE_ID) {
            result << makePlayItem();
        } else if (item.intent == DRUMS_MUTE_ID) {
            result << makeDrumsMuteItem();
        } else if (item.intent == ACCOMPANIMENT_MUTE_ID) {
            result << makeAccompanimentMuteItem();
        } else {
            const rcommand::Command command(item.intent);
            if (isAdditionalCommand(command) && !m_isToolbarFloating && !studioPlayerMode) {
                //! NOTE In this case, we want to see the actions' description instead of the title
                settingsItems << makeMenuItem(command);
            } else {
                result << makeMenuItem(command);
            }
        }
    }

    if (studioPlayerMode) {
        result << makeMenuItem(REPEATS_TOGGLE_COMMAND);
    } else {
        MenuItem* settingsItem = makeMenu(TranslatableString("action", "播放设置"), settingsItems);
        settingsItem->setIcon(ui::IconCode::Code::SETTINGS_COG);
        result << settingsItem;
    }

    setItems(result);
}

MenuItem* PlaybackToolBarModel::makeInputPitchMenu()
{
    MenuItemList items = {
        makeMenuItem(MIDI_INPUT_WRITTEN_PITCH_COMMAND),
        makeMenuItem(MIDI_INPUT_SOUNDING_PITCH_COMMAND),
    };

    MenuItem* menu = makeMenu(muse::TranslatableString("playback", "MIDI 输入音高"), items);
    menu->setIcon(ui::IconCode::Code::MUSIC_NOTES);
    return menu;
}

MenuItem* PlaybackToolBarModel::makeDrumsMuteItem()
{
    MenuItem* item = new MenuItem(this);
    item->setId(DRUMS_MUTE_ID);
    item->setTitle(TranslatableString("playback", "鼓声"));
    item->setDescription(TranslatableString("playback", "切换鼓声静音"));
    item->setIcon(ui::IconCode::Code::PERCUSSION);
    item->setCheckable(true);
    item->setChecked(m_drumsMuted);
    return item;
}

void PlaybackToolBarModel::updateDrumsMuteItem()
{
    MenuItem& item = findItem(DRUMS_MUTE_ID);
    if (item.isValid()) {
        item.setChecked(m_drumsMuted);
    }
}

MenuItem* PlaybackToolBarModel::makeAccompanimentMuteItem()
{
    MenuItem* item = new MenuItem(this);
    item->setId(ACCOMPANIMENT_MUTE_ID);
    item->setTitle(TranslatableString("playback", "伴奏"));
    item->setDescription(TranslatableString("playback", "切换伴奏静音"));
    item->setIcon(ui::IconCode::Code::AUDIO);
    item->setCheckable(true);
    item->setChecked(m_accompanimentMuted);
    return item;
}

void PlaybackToolBarModel::updateAccompanimentMuteItem()
{
    MenuItem& item = findItem(ACCOMPANIMENT_MUTE_ID);
    if (item.isValid()) {
        item.setChecked(m_accompanimentMuted);
    }
}

void PlaybackToolBarModel::setDrumsMuted(bool muted)
{
    if (m_drumsMuted == muted) {
        return;
    }
    m_drumsMuted = muted;
    applyDrumsMute(muted);
    updateDrumsMuteItem();
}

void PlaybackToolBarModel::setAccompanimentMuted(bool muted)
{
    if (m_accompanimentMuted == muted) {
        return;
    }
    m_accompanimentMuted = muted;
    applyAccompanimentMute(muted);
    updateAccompanimentMuteItem();
}

bool PlaybackToolBarModel::isAdditionalCommand(const muse::rcommand::Command& command) const
{
    static const std::vector<muse::rcommand::Command> additionalCommands = {
        LOOP_IN_COMMAND,
        LOOP_OUT_COMMAND,
    };

    return muse::contains(additionalCommands, command);
}

bool PlaybackToolBarModel::isPlayAllowed() const
{
    return playbackController()->isPlayAllowed();
}

bool PlaybackToolBarModel::isToolbarFloating() const
{
    return m_isToolbarFloating;
}

void PlaybackToolBarModel::setIsToolbarFloating(bool floating)
{
    if (floating == m_isToolbarFloating) {
        return;
    }

    m_isToolbarFloating = floating;
    emit isToolbarFloatingChanged(floating);
}

QTime PlaybackToolBarModel::maxPlayTime() const
{
    return timeFromSeconds(totalPlayTime());
}

QTime PlaybackToolBarModel::playTime() const
{
    return timeFromSeconds(m_playbackPositionSecs);
}

void PlaybackToolBarModel::setPlayTime(const QTime& time)
{
    rewind(timeToSeconds(time));
}

qreal PlaybackToolBarModel::playPosition() const
{
    const secs_t totalSecs = totalPlayTime();
    if (totalSecs.is_zero()) {
        return 0.0;
    }

    const qreal position = static_cast<qreal>(m_playbackPositionSecs) / static_cast<qreal>(totalSecs);
    return position;
}

void PlaybackToolBarModel::setPlayPosition(qreal position)
{
    rewind(totalPlayTime() * position);
}

secs_t PlaybackToolBarModel::totalPlayTime() const
{
    return playbackController()->totalPlayTime();
}

MeasureBeat PlaybackToolBarModel::measureBeat() const
{
    return playbackController()->currentBeat();
}

muse::uicomponents::MenuItem* PlaybackToolBarModel::makePlayItem()
{
    rcommand::Command command = globalContext()->playbackState()->isPlaying() ? PAUSE_COMMAND : PLAY_COMMAND;
    MenuItem* item = makeMenuItem(command);
    item->setId(PLAY_TOGGLE_ID);
    return item;
}

void PlaybackToolBarModel::updatePlayItem()
{
    MenuItem& item = findItem(PLAY_TOGGLE_ID);
    if (item.isValid()) {
        rcommand::Command command = globalContext()->playbackState()->isPlaying() ? PAUSE_COMMAND : PLAY_COMMAND;
        item.setCommandInfo(commandsRegister()->commandInfo(command));
        item.setId(PLAY_TOGGLE_ID);
    }
}

void PlaybackToolBarModel::updatePlayPosition(secs_t secs)
{
    if (m_playbackPositionSecs == secs) {
        return;
    }

    m_playbackPositionSecs = secs;
    emit playPositionChanged();
}

void PlaybackToolBarModel::rewind(secs_t secs)
{
    if (secs > totalPlayTime()) {
        return;
    }

    dispatchCommand(REWIND_COMMAND, { { "position", Val(secs) } });
}

void PlaybackToolBarModel::rewindToStart()
{
    playbackController()->rewind(muse::secs_t(0));
    m_playbackPositionSecs = 0.0;
    emit playPositionChanged();
}

void PlaybackToolBarModel::handleMenuItem(const QString& itemId)
{
    if (itemId == "command://playback/rewind") {
        rewindToStart();
        return;
    }

    if (itemId == DRUMS_MUTE_ID) {
        setDrumsMuted(!m_drumsMuted);
        return;
    }

    if (itemId == ACCOMPANIMENT_MUTE_ID) {
        setAccompanimentMuted(!m_accompanimentMuted);
        return;
    }

    if (itemId == "command://playback/loop-in") {
        toggleLoopMarker(LoopBoundaryType::LoopIn);
        return;
    }

    if (itemId == "command://playback/loop-out") {
        toggleLoopMarker(LoopBoundaryType::LoopOut);
        return;
    }

    AbstractMenuModel::handleMenuItem(itemId);
}

void PlaybackToolBarModel::toggleLoopMarker(LoopBoundaryType type)
{
    const notation::INotationPtr notation = globalContext()->currentNotation();
    const notation::INotationPlaybackPtr playback =
        notation ? notation->masterNotation()->playback() : nullptr;
    Score* score = notation ? notation->elements()->msScore() : nullptr;
    if (!playback || !score || !score->firstMeasure() || !score->lastMeasure()) {
        return;
    }

    const Fraction firstTick = score->firstMeasure()->tick();
    const Fraction lastTick = score->lastMeasure()->endTick();
    const notation::LoopBoundaries boundaries = playback->loopBoundaries();
    const bool inSet = boundaries.loopInSet;
    const bool outSet = boundaries.loopOutSet;

    if (type == LoopBoundaryType::LoopIn) {
        if (inSet) {
            score->setLoopInTick(firstTick);
        } else {
            playbackController()->addLoopBoundary(type);
            return;
        }
    } else if (type == LoopBoundaryType::LoopOut) {
        if (outSet) {
            score->setLoopOutTick(lastTick);
        } else {
            playbackController()->addLoopBoundary(type);
            return;
        }
    } else {
        return;
    }

    const bool keepLoop = type == LoopBoundaryType::LoopIn ? outSet : inSet;
    playback->setLoopBoundarySet(type, false);
    playback->setLoopBoundariesEnabled(keepLoop);
}

void PlaybackToolBarModel::applyDrumsMute(bool muted)
{
    notation::IMasterNotationPtr masterNotation = globalContext()->currentMasterNotation();
    if (!masterNotation) {
        return;
    }

    const async::NotifyList<const Part*> parts = masterNotation->parts()->partList();
    for (const Part* part : parts) {
        if (!part || !part->instrument() || !part->instrument()->drumset()) {
            continue;
        }

        for (const InstrumentTrackId& trackId : part->instrumentTrackIdList()) {
            IPlaybackController::SoloMuteState state = playbackController()->trackSoloMuteState(trackId);
            state.mute = muted;
            playbackController()->setTrackSoloMuteState(trackId, state);
        }
    }
}

void PlaybackToolBarModel::applyAccompanimentMute(bool muted)
{
    project::INotationProjectPtr project = globalContext()->currentProject();
    project::IProjectAudioSettingsPtr audioSettings = project ? project->audioSettings() : nullptr;
    if (!audioSettings) {
        return;
    }

    project::AudioTrackSettings settings = audioSettings->audioTrackSettings();
    bool changed = false;
    for (project::AudioClipSettings& clip : settings.clips) {
        if (clip.muted != muted) {
            clip.muted = muted;
            changed = true;
        }
    }
    if (changed) {
        audioSettings->setAudioTrackSettings(settings);
    }
}

void PlaybackToolBarModel::rewindToBeat(const MeasureBeat& beat)
{
    secs_t secs = playbackController()->beatToSecs(beat.measureIndex, static_cast<int>(beat.beat));
    rewind(secs);
}

int PlaybackToolBarModel::measureNumber() const
{
    return measureBeat().measureIndex + 1;
}

void PlaybackToolBarModel::setMeasureNumber(int measureNumber)
{
    int measureIndex = measureNumber - 1;
    MeasureBeat measureBeat = this->measureBeat();

    if (measureIndex == measureBeat.measureIndex) {
        return;
    }

    measureBeat.measureIndex = measureIndex;
    rewindToBeat(measureBeat);
}

int PlaybackToolBarModel::maxMeasureNumber() const
{
    return measureBeat().maxMeasureIndex + 1;
}

int PlaybackToolBarModel::beatNumber() const
{
    return static_cast<int>(measureBeat().beat) + 1;
}

void PlaybackToolBarModel::setBeatNumber(int beatNumber)
{
    int beatIndex = beatNumber - 1;
    MeasureBeat measureBeat = this->measureBeat();

    if (beatIndex == static_cast<int>(measureBeat.beat)) {
        return;
    }

    measureBeat.beat = beatIndex;
    rewindToBeat(measureBeat);
}

void PlaybackToolBarModel::setTempoMultiplier(qreal multiplier)
{
    // DB Player: notation events, metronome and accompaniment share one rate.
    multiplier = qBound<qreal>(0.01, multiplier, 10.0);

    // Refresh the controller cache even when returning to the original tempo.
    playbackController()->setTempoMultiplier(multiplier);
    emit tempoChanged();
}

void PlaybackToolBarModel::setTempoBpm(int bpm)
{
    const int currentBpm = tempoBpm();
    if (bpm <= 0 || currentBpm <= 0) {
        return;
    }

    const qreal nextMultiplier = tempoMultiplier() * qreal(bpm) / qreal(currentBpm);
    setTempoMultiplier(nextMultiplier);
}

void PlaybackToolBarModel::resetTempo()
{
    setTempoMultiplier(1.0);
}

int PlaybackToolBarModel::maxBeatNumber() const
{
    return measureBeat().maxBeatIndex + 1;
}

QVariant PlaybackToolBarModel::tempo() const
{
    static const std::unordered_map<DurationType, MusicalSymbolCodes::Code> DURATION_TO_ICON {
        { DurationType::V_WHOLE, MusicalSymbolCodes::Code::SEMIBREVE },
        { DurationType::V_HALF, MusicalSymbolCodes::Code::MINIM },
        { DurationType::V_QUARTER, MusicalSymbolCodes::Code::CROTCHET },
        { DurationType::V_EIGHTH, MusicalSymbolCodes::Code::QUAVER },
        { DurationType::V_16TH, MusicalSymbolCodes::Code::SEMIQUAVER },
    };

    const notation::Tempo& tempo = playbackController()->currentTempo();
    const MusicalSymbolCodes::Code noteIcon = muse::value(DURATION_TO_ICON, tempo.duration,
                                                          MusicalSymbolCodes::Code::CROTCHET);

    QVariantMap obj;
    obj["noteSymbol"] = musicalSymbolToString(noteIcon, tempo.withDot);
    obj["value"] = tempo.valueBpm;

    return obj;
}

int PlaybackToolBarModel::tempoBpm() const
{
    return tempo().toMap().value("value").toInt();
}

qreal PlaybackToolBarModel::tempoMultiplier() const
{
    return playbackController()->tempoMultiplier();
}

QColor PlaybackToolBarModel::playbackCursorColor() const
{
    return notationConfiguration()->playbackCursorColor();
}

qreal PlaybackToolBarModel::playbackCursorThickness() const
{
    return notationConfiguration()->playbackCursorThickness();
}

qreal PlaybackToolBarModel::playbackCursorOpacity() const
{
    return notationConfiguration()->playbackCursorOpacity();
}

qreal PlaybackToolBarModel::playbackCursorLength() const
{
    return notationConfiguration()->playbackCursorLength();
}

void PlaybackToolBarModel::setPlaybackCursorColor(const QColor& color)
{
    if (color == playbackCursorColor()) {
        return;
    }

    notationConfiguration()->setPlaybackCursorColor(color);
    emit playbackCursorStyleChanged();
}

void PlaybackToolBarModel::setPlaybackCursorThickness(qreal thickness)
{
    if (muse::RealIsEqual(thickness, playbackCursorThickness())) {
        return;
    }

    notationConfiguration()->setPlaybackCursorThickness(thickness);
    emit playbackCursorStyleChanged();
}

void PlaybackToolBarModel::setPlaybackCursorOpacity(qreal opacity)
{
    if (muse::RealIsEqual(opacity, playbackCursorOpacity())) {
        return;
    }

    notationConfiguration()->setPlaybackCursorOpacity(opacity);
    emit playbackCursorStyleChanged();
}

void PlaybackToolBarModel::setPlaybackCursorLength(qreal length)
{
    if (muse::RealIsEqual(length, playbackCursorLength())) {
        return;
    }

    notationConfiguration()->setPlaybackCursorLength(length);
    emit playbackCursorStyleChanged();
}
