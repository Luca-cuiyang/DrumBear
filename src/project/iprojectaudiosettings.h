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

#pragma once

#include <memory>
#include <vector>

#include "async/notification.h"
#include "audio/common/audiotypes.h"
#include "engraving/types/types.h"
#include "global/io/path.h"
#include "playback/playbacktypes.h"
#include "notation/inotationsolomutestate.h"

namespace mu::project {
using AudioInputParams = muse::audio::AudioInputParams;
using TrackInputParamsMap = std::unordered_map<engraving::InstrumentTrackId, AudioInputParams>;

struct AudioClipSettings {
    muse::io::path_t filePath;
    muse::secs_t startOffset = 0.0;   //! score time (seconds) at which the audio starts playing
    muse::secs_t clipStart = 0.0;     //! crop start within the audio file (seconds)
    muse::secs_t clipEnd = 0.0;       //! crop end within the audio file (seconds); 0 means until the end
    muse::audio::volume_db_t volume = 0.f;
    bool muted = false;
    float speed = 1.f;
    muse::secs_t fadeIn = 0.0;
    muse::secs_t fadeOut = 0.0;

    bool isValid() const { return !filePath.empty(); }

    bool operator==(const AudioClipSettings& other) const
    {
        return filePath == other.filePath
               && muse::is_equal(startOffset, other.startOffset)
               && muse::is_equal(clipStart, other.clipStart)
               && muse::is_equal(clipEnd, other.clipEnd)
               && muse::is_equal(volume, other.volume)
               && muted == other.muted
               && muse::is_equal(speed, other.speed)
               && muse::is_equal(fadeIn, other.fadeIn)
               && muse::is_equal(fadeOut, other.fadeOut);
    }
};

struct AudioTrackSettings {
    std::vector<AudioClipSettings> clips;

    bool isValid() const { return !clips.empty(); }

    bool operator==(const AudioTrackSettings& other) const
    {
        return clips == other.clips;
    }
};

//! NOTE This model (structure) is not used in the audio module, there are other models.
struct AudioOutputParams {
    muse::audio::AudioFxChain fxChain;
    muse::audio::volume_db_t volume = 0.f;
    muse::audio::balance_t balance = 0.f;
    muse::audio::AuxSendsParams auxSends;
    bool solo = false;
    bool muted = false;
    bool forceMute = false;

    bool operator ==(const AudioOutputParams& other) const
    {
        return fxChain == other.fxChain
               && muse::is_equal(volume, other.volume)
               && muse::is_equal(balance, other.balance)
               && auxSends == other.auxSends
               && solo == other.solo
               && muted == other.muted
               && forceMute == other.forceMute;
    }

    muse::audio::ControlParams control() const
    {
        muse::audio::ControlParams control;
        control.volume = volume;
        control.balance = balance;
        control.muted = muted;
        return control;
    }

    void setControl(const muse::audio::ControlParams& control)
    {
        if (!control.volume.hasAutomation()) {
            volume = std::get<muse::audio::volume_db_t>(control.volume.value());
        }
        if (!control.balance.hasAutomation()) {
            balance = std::get<muse::audio::balance_t>(control.balance.value());
        }
        muted = control.muted;
    }
};

class IProjectAudioSettings
{
public:
    using SoloMuteState = notation::INotationSoloMuteState::SoloMuteState;

    virtual ~IProjectAudioSettings() = default;

    virtual bool hasAnyAudioSettings() const = 0;

    virtual const AudioOutputParams& masterAudioOutputParams() const = 0;
    virtual void setMasterAudioOutputParams(const AudioOutputParams& params) = 0;

    virtual bool containsAuxOutputParams(muse::audio::aux_channel_idx_t index) const = 0;
    virtual const AudioOutputParams& auxOutputParams(muse::audio::aux_channel_idx_t index) const = 0;
    virtual void setAuxOutputParams(muse::audio::aux_channel_idx_t index, const AudioOutputParams& params,
                                    bool notifySettingsChanged = true) = 0;

    virtual const TrackInputParamsMap& allTrackInputParams() const = 0;
    virtual const AudioInputParams& trackInputParams(const engraving::InstrumentTrackId& trackId) const = 0;
    virtual void setTrackInputParams(const engraving::InstrumentTrackId& trackId, const AudioInputParams& params,
                                     bool notifySettingsChanged = true) = 0;
    virtual void clearTrackInputParams() = 0;
    virtual muse::async::Channel<engraving::InstrumentTrackId> trackInputParamsChanged() const = 0;

    virtual bool trackHasExistingOutputParams(const engraving::InstrumentTrackId& trackId) const = 0;
    virtual const AudioOutputParams& trackOutputParams(const engraving::InstrumentTrackId& trackId) const = 0;
    virtual void setTrackOutputParams(const engraving::InstrumentTrackId& trackId, const AudioOutputParams& params,
                                      bool notifySettingsChanged = true) = 0;

    virtual const SoloMuteState& auxSoloMuteState(muse::audio::aux_channel_idx_t index) const = 0;
    virtual void setAuxSoloMuteState(muse::audio::aux_channel_idx_t index, const SoloMuteState& state) = 0;
    virtual muse::async::Channel<muse::audio::aux_channel_idx_t, SoloMuteState> auxSoloMuteStateChanged() const = 0;

    virtual void removeTrackParams(const engraving::InstrumentTrackId& trackId) = 0;

    virtual const AudioTrackSettings& audioTrackSettings() const = 0;
    virtual void setAudioTrackSettings(const AudioTrackSettings& settings) = 0;
    virtual muse::async::Notification audioTrackSettingsChanged() const = 0;

    virtual const playback::SoundProfileName& activeSoundProfile() const = 0;
    virtual void setActiveSoundProfile(const playback::SoundProfileName& profileName) = 0;

    virtual muse::async::Notification settingsChanged() const = 0;
};

using IProjectAudioSettingsPtr = std::shared_ptr<IProjectAudioSettings>;
}
