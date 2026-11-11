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
#include "videowriter.h"

#include <algorithm>
#include <cmath>

#include <QPainter>
#include <QEventLoop>
#include <QThread>
#include <QTimer>

#include "global/concurrency/concurrent.h"
#include "global/io/filestream.h"

#include "draw/fontmetrics.h"
#include "draw/painter.h"
#include "draw/types/drawtypes.h"

#include "engraving/dom/box.h"
#include "engraving/dom/masterscore.h"
#include "engraving/dom/page.h"
#include "engraving/dom/repeatlist.h"
#include "engraving/dom/system.h"
#include "engraving/dom/text.h"
#include "engraving/dom/textbase.h"

#include "notation/imasternotation.h"
#include "notation/inotation.h"
#include "notation/inotationelements.h" // IWYU pragma: keep
#include "notation/inotationpainting.h"
#include "notation/inotationplayback.h"
#include "notation/notationtypes.h"

#include "notationscene/qml/MuseScore/NotationScene/playbackcursor.h"

#include "defer.h"
#include "log.h"

using namespace mu::iex::videoexport;
using namespace mu::project;
using namespace mu::notation;
using namespace muse::draw;
using namespace muse::midi;

namespace {
// Locked DB Studio drum-player layout contract.
constexpr double DB_STUDIO_PAGE_MARGIN_MM = 5.0;
constexpr double DB_STUDIO_PAGE_WIDTH_MM = 210.0;
constexpr double DB_STUDIO_PAGE_HEIGHT_MM = 297.0;
constexpr double DB_STUDIO_PRINTABLE_WIDTH_MM = DB_STUDIO_PAGE_WIDTH_MM - 2.0 * DB_STUDIO_PAGE_MARGIN_MM;
constexpr double DB_STUDIO_SPATIUM_MM = 1.75;
constexpr double DB_STUDIO_SYSTEM_DISTANCE_SP = 10.6;
constexpr double DB_STUDIO_TITLE_TO_SYSTEM_DISTANCE_SP = 8.0;
constexpr double DB_STUDIO_TITLE_FRAME_HEIGHT_SP = 3.5;
constexpr double DB_STUDIO_TEMPO_FONT_SIZE = 12.0;
constexpr double DB_STUDIO_MEASURE_NUMBER_FONT_SIZE = 7.0;
constexpr double DB_STUDIO_TITLE_FONT_SIZE_PT = 16.0;
constexpr double DB_STUDIO_STAFF_TEXT_FONT_SIZE = 10.0;
constexpr double DB_STUDIO_SYSTEM_TEXT_FONT_SIZE = 10.0;
constexpr double DB_STUDIO_REHEARSAL_MARK_FONT_SIZE = 14.0;
constexpr double DB_STUDIO_PLAYBACK_FOLLOW_INTERVAL_SEC = 0.008;
constexpr double DB_STUDIO_PLAYBACK_FOLLOW_INTERPOLATION = 0.14;
constexpr double DB_STUDIO_PLAYBACK_FOLLOW_EPSILON = 0.15;
constexpr int DB_STUDIO_PLAYBACK_SCROLL_SYSTEM_INTERVAL = 2;
constexpr double DB_STUDIO_PLAYBACK_EXTRA_DISTANCE_SP = 11.5;
constexpr int DB_STUDIO_PLAYBACK_TRIGGER_MEASURE = 3;

double dbStudioPageMarginInches()
{
    return DB_STUDIO_PAGE_MARGIN_MM / mu::engraving::INCH;
}

void applyDbStudioLandscapeStyle(mu::engraving::Score* score)
{
    mu::engraving::MStyle& style = score->style();
    const double pageMargin = dbStudioPageMarginInches();

    style.set(mu::engraving::Sid::spatium, DB_STUDIO_SPATIUM_MM * mu::engraving::DPMM);
    style.set(mu::engraving::Sid::pageEvenLeftMargin, pageMargin);
    style.set(mu::engraving::Sid::pageOddLeftMargin, pageMargin);
    style.set(mu::engraving::Sid::pageEvenTopMargin, pageMargin);
    style.set(mu::engraving::Sid::pageEvenBottomMargin, pageMargin);
    style.set(mu::engraving::Sid::pageOddTopMargin, pageMargin);
    style.set(mu::engraving::Sid::pageOddBottomMargin, pageMargin);
    style.set(mu::engraving::Sid::pageTwosided, false);

    style.set(mu::engraving::Sid::enableVerticalSpread, false);
    style.set(mu::engraving::Sid::staffUpperBorder, mu::engraving::Spatium(6.2));
    style.set(mu::engraving::Sid::staffLowerBorder, mu::engraving::Spatium(6.2));
    style.set(mu::engraving::Sid::staffLineWidth, mu::engraving::Spatium(0.125));
    style.set(mu::engraving::Sid::barWidth, mu::engraving::Spatium(0.1875));
    style.set(mu::engraving::Sid::minSystemDistance, mu::engraving::Spatium(DB_STUDIO_SYSTEM_DISTANCE_SP));
    style.set(mu::engraving::Sid::maxSystemDistance, mu::engraving::Spatium(DB_STUDIO_SYSTEM_DISTANCE_SP));
    style.set(mu::engraving::Sid::systemFrameDistance, mu::engraving::Spatium(0.0));
    style.set(mu::engraving::Sid::frameSystemDistance, mu::engraving::Spatium(DB_STUDIO_TITLE_TO_SYSTEM_DISTANCE_SP));
    style.set(mu::engraving::Sid::enableIndentationOnFirstSystem, false);

    style.set(mu::engraving::Sid::tempoFontSize, DB_STUDIO_TEMPO_FONT_SIZE);
    style.set(mu::engraving::Sid::tempoFontSpatiumDependent, true);
    style.set(mu::engraving::Sid::measureNumberFontSize, DB_STUDIO_MEASURE_NUMBER_FONT_SIZE);
    style.set(mu::engraving::Sid::measureNumberFontSpatiumDependent, false);
    style.set(mu::engraving::Sid::titleFontSize, DB_STUDIO_TITLE_FONT_SIZE_PT);
    style.set(mu::engraving::Sid::titleFontSpatiumDependent, false);

    style.set(mu::engraving::Sid::showHeader, false);
    style.set(mu::engraving::Sid::showFooter, false);
    style.set(mu::engraving::Sid::showPageNumber, false);
    style.set(mu::engraving::Sid::showPageNumberOne, false);
    style.set(mu::engraving::Sid::lyricsOddPosition, mu::engraving::AlignH::HCENTER);
    style.set(mu::engraving::Sid::lyricsEvenPosition, mu::engraving::AlignH::HCENTER);

    score->styleChanged();
}

void applyDbStudioLandscapePageSize(mu::engraving::Score* score)
{
    mu::engraving::MStyle& style = score->style();
    style.set(mu::engraving::Sid::pageWidth, DB_STUDIO_PAGE_WIDTH_MM / mu::engraving::INCH);
    style.set(mu::engraving::Sid::pageHeight, DB_STUDIO_PAGE_HEIGHT_MM / mu::engraving::INCH);
    style.set(mu::engraving::Sid::pagePrintableWidth, DB_STUDIO_PRINTABLE_WIDTH_MM / mu::engraving::INCH);
}

bool isLandscapeVideo(int width, int height)
{
    return width > height;
}

muse::RectF visibleSystemBoundingBox(const mu::engraving::System* system)
{
    muse::RectF result = system->pageBoundingRect();

    //! Title glyphs may extend above the title frame's geometric bbox.
    if (const mu::engraving::Box* box = system->vbox(); box && box->isTBox()) {
        if (const mu::engraving::Text* title = mu::engraving::toTBox(box)->text()) {
            result.unite(title->pageBoundingRect());
        }
    }

    //! Staff lines are the hard lower boundary. Their geometric extent is not
    //! always identical to the system bbox, especially on the final system.
    for (const mu::engraving::SysStaff* staff : system->staves()) {
        if (staff && staff->show() && !staff->bbox().isEmpty()) {
            result.unite(staff->bbox().translated(system->pagePos()));
        }
    }
    return result;
}
}

static muse::String notationTitle(const INotationPtr notation)
{
    muse::String title;
    mu::engraving::Score* score = notation->elements()->msScore();
    mu::engraving::MasterScore* masterScore = notation->masterNotation()->masterScore();

    if (const mu::engraving::Text* text = score->getText(mu::engraving::TextStyleType::TITLE)) {
        title = text->plainText();
    }

    if (title.isEmpty()) {
        if (const mu::engraving::Text* text = masterScore->getText(mu::engraving::TextStyleType::TITLE)) {
            title = text->plainText();
        }
    }

    if (title.isEmpty()) {
        title = masterScore->metaTag(u"workTitle");
    }

    return title;
}

static muse::String notationSubtitle(const INotationPtr notation)
{
    if (notation->isMaster()) {
        return muse::String();
    }

    return notation->name();
}

std::vector<INotationWriter::UnitType> VideoWriter::supportedUnitTypes() const
{
    return { UnitType::PER_PART };
}

bool VideoWriter::supportsUnitType(UnitType unitType) const
{
    std::vector<UnitType> unitTypes = supportedUnitTypes();
    return std::find(unitTypes.cbegin(), unitTypes.cend(), unitType) != unitTypes.cend();
}

muse::Ret VideoWriter::write(INotationPtr notation, muse::io::IODevice& device, const Options& options)
{
    if (!authorization() || !authorization()->hasProAccess()) {
        return make_ret(muse::Ret::Code::UnknownError, std::string("导出 MP4 视频需要开通会员"));
    }

    std::string filePath = device.meta("file_path");
    IF_ASSERT_FAILED(!filePath.empty()) {
        return make_ret(muse::Ret::Code::InternalError);
    }

    bool withAudio = muse::value(options, OptionKey::WITH_AUDIO, muse::Val(configuration()->includeAudio())).toBool();

    Config cfg = makeConfig();

    muse::io::path_t finalPath(filePath);
    muse::io::path_t tempAudioPath = finalPath + ".tmp_audio.aac";

    auto encoder = videoEncodeResolver()->currentVideoEncoder();

    muse::media::IVideoEncoder::Options encoderOptions;
    encoderOptions.format = "mp4";
    encoderOptions.width = cfg.width;
    encoderOptions.height = cfg.height;
    encoderOptions.bitrate = cfg.bitrate;
    encoderOptions.gop = cfg.fps / 2;
    encoderOptions.fps = cfg.fps;

    if (!encoder->open(finalPath, encoderOptions)) {
        LOGE() << "failed to open video encoder";
        return make_ret(muse::Ret::Code::UnknownError);
    }

    m_isCompleted = false;
    m_audioCompleted = false;
    m_abort = false;
    m_writeRet = muse::Ret();
    m_audioRet = muse::Ret();

    startVideoExport(encoder, notation, cfg);

    if (withAudio) {
        startAudioExport(notation, tempAudioPath, cfg);
    } else {
        m_audioCompleted = true;
        m_audioRet = muse::make_ok();
    }

    //! NOTE: 用事件循环按小间隔等待，替代忙轮询，避免导出期间主线程空转占满 CPU。
    while (!m_isCompleted || !m_audioCompleted) {
        QEventLoop loop;
        QTimer::singleShot(16, &loop, &QEventLoop::quit);
        loop.exec();
    }

    if (m_audioWriter) {
        m_audioWriter->progress()->finished().disconnect(this);
        m_audioWriter = nullptr;
    }

    if (m_audioFile) {
        m_audioFile->close();
        m_audioFile.reset();
    }

    muse::Ret result = m_writeRet;

    encoder->finishEncode();

    // Release the device's file handle before add audio replaces the file
    device.close();

    if (withAudio) {
        if (result && m_audioRet) {
            if (!encoder->addAudio(tempAudioPath)) {
                result = make_ret(muse::Ret::Code::UnknownError);
            }
        } else if (!result) {
            // keep video error
        } else {
            result = m_audioRet;
        }

        fileSystem()->remove(tempAudioPath);
    }

    encoder->close();

    return result;
}

VideoWriter::Config VideoWriter::makeConfig() const
{
    Config cfg;

    cfg.fps = configuration()->fps();

    std::string resolution = configuration()->resolution();
    if (resolution == "1080p_16x9") {
        cfg.width = 1920;
        cfg.height = 1080;
    } else if (resolution == "1080p_9x16") {
        cfg.width = 1080;
        cfg.height = 1920;
    } else if (resolution == "2k_16x9") {
        cfg.width = 2560;
        cfg.height = 1440;
    } else if (resolution == "2k_9x16") {
        cfg.width = 1440;
        cfg.height = 2560;
    } else if (resolution == "4k_16x9") {
        cfg.width = 3840;
        cfg.height = 2160;
    } else if (resolution == "4k_9x16") {
        cfg.width = 2160;
        cfg.height = 3840;
    } else if (resolution == "1080p") {
        cfg.width = 1920;
        cfg.height = 1080;
    } else if (resolution == "720p") {
        cfg.width = 1280;
        cfg.height = 720;
    } else if (resolution == "480p") {
        cfg.width = 854;
        cfg.height = 480;
    } else if (resolution == "360p") {
        cfg.width = 640;
        cfg.height = 360;
    } else {
        cfg.width = 1920;
        cfg.height = 1080;
    }

    // compute bitrate according to Google recommended settings
    // https://support.google.com/youtube/answer/1722171?hl=en
    //! NOTE: 按总像素数分级，横竖屏同一档分辨率（如 4K 16:9 与 4K 9:16）得到相同码率，
    //! 修复此前竖屏因 height 不同落入默认 8Mbps、导致 4K 竖屏码率过低画面发糊的问题。
    const long long pixels = static_cast<long long>(cfg.width) * cfg.height;
    float br = 8;
    if (pixels >= 3840LL * 2160) {
        br = cfg.fps < 35 ? 40 : 60;
    } else if (pixels >= 2560LL * 1440) {
        br = cfg.fps < 35 ? 16 : 24;
    } else if (pixels >= 1920LL * 1080) {
        br = cfg.fps < 35 ? 10 : 15;
    } else if (pixels >= 1280LL * 720) {
        br = cfg.fps < 35 ? 5 : 7.5;
    } else if (pixels >= 854LL * 480) {
        br = cfg.fps < 35 ? 2.5 : 4;
    } else {
        br = cfg.fps < 35 ? 1 : 1.5;
    }
    cfg.bitrate = int(br * 1000000);

    // 片头封面与片尾停留全部关闭：视频从第一帧起就是乐谱画面，播放结束立即结束。
    cfg.leadingSec = 0.0;
    cfg.trailingSec = 0.0;

    cfg.viewMode = configuration()->viewMode();
    cfg.smoothPageTransitions = configuration()->smoothPageTransitions();

    return cfg;
}

void VideoWriter::startVideoExport(muse::media::IVideoEncoderPtr encoder, INotationPtr notation, const Config& cfg)
{
    muse::Concurrent::run([this, encoder, notation, cfg]() {
        doGenerate(encoder, notation, cfg);
    });
}

void VideoWriter::startAudioExport(INotationPtr notation, const muse::io::path_t& audioPath, const Config& cfg)
{
    m_audioWriter = writers()->writer("aac");
    if (!m_audioWriter) {
        LOGE() << "aac writer not found";
        m_audioRet = make_ret(muse::Ret::Code::InternalError);
        m_audioCompleted = true;
        return;
    }

    m_audioWriter->progress()->finished().onReceive(this, [this](const muse::ProgressResult& res) {
        m_audioRet = res.ret;
        m_audioCompleted = true;
    });

    Options audioOpts;
    audioOpts[OptionKey::WAIT_FOR_COMPLETION] = muse::Val(false);
    audioOpts[OptionKey::LEADING_SILENCE_SEC] = muse::Val(static_cast<double>(cfg.leadingSec));
    audioOpts[OptionKey::TRAILING_SILENCE_SEC] = muse::Val(static_cast<double>(cfg.trailingSec));

    m_audioFile = std::make_unique<muse::io::FileStream>(audioPath);
    m_audioFile->setMeta("file_path", audioPath.toStdString());
    m_audioFile->open(muse::io::IODevice::WriteOnly);

    m_audioWriter->write(notation, *m_audioFile, audioOpts);
}

muse::Ret VideoWriter::writeList(const INotationPtrList&, muse::io::IODevice&, const Options&)
{
    NOT_SUPPORTED;
    return make_ret(muse::Ret::Code::NotSupported);
}

muse::Progress* VideoWriter::progress()
{
    return &m_progress;
}

void VideoWriter::abort()
{
    m_abort = true;

    if (m_audioWriter) {
        m_audioWriter->abort();
    }

    // Wait abort completion（同样用事件循环替代忙轮询）
    while (!m_isCompleted || !m_audioCompleted) {
        QEventLoop loop;
        QTimer::singleShot(16, &loop, &QEventLoop::quit);
        loop.exec();
    }
}

std::optional<VideoWriter::ScoreRestoreData> VideoWriter::prepareScore(INotationPtr notation, Config& config)
{
    ScoreRestoreData result;
    engraving::Score* score = notation->elements()->msScore();
    const bool landscape = isLandscapeVideo(config.width, config.height);

    result.style = score->style();

    result.layoutMode = score->layoutMode();

    result.showFrames = score->showFrames();
    result.showInstrumentNames = score->showInstrumentNames();
    result.showInvisible = score->isShowInvisible();
    result.showPageborders = score->showPageborders();
    result.showUnprintable = score->showUnprintable();
    result.showVBox = score->layoutOptions().isShowVBox;

    score->setLayoutMode(engraving::LayoutMode::PAGE);

    //! 导出视频统一行距：关闭「竖向散布」。否则行距走 min/maxSystemSpread（默认 8.5~32），
    //! 内容、分节、方括号都会把各行间距撑得时宽时窄；关闭后改用 min/maxSystemDistance 控制。
    score->style().set(engraving::Sid::enableVerticalSpread, false);

    if (landscape) {
        applyDbStudioLandscapePageSize(score);
        applyDbStudioLandscapeStyle(score);

        // Imported scores often carry explicit per-text font sizes that override
        // the video style. Normalize only the structural labels that otherwise
        // become oversized in 4K landscape exports, and preserve the original
        // rich text so the editor is restored unchanged after export.
        score->scanElements([&result](engraving::EngravingItem* item) {
            engraving::TextBase* text = dynamic_cast<engraving::TextBase*>(item);
            if (!text) {
                return;
            }

            double targetSize = -1.0;
            switch (text->textStyleType()) {
            case engraving::TextStyleType::TITLE:
                targetSize = DB_STUDIO_TITLE_FONT_SIZE_PT;
                break;
            case engraving::TextStyleType::STAFF:
                targetSize = DB_STUDIO_STAFF_TEXT_FONT_SIZE;
                break;
            case engraving::TextStyleType::SYSTEM:
                targetSize = DB_STUDIO_SYSTEM_TEXT_FONT_SIZE;
                break;
            case engraving::TextStyleType::REHEARSAL_MARK:
                targetSize = DB_STUDIO_REHEARSAL_MARK_FONT_SIZE;
                break;
            default:
                return;
            }

            if (text->size() <= targetSize) {
                return;
            }

            result.normalizedTexts.push_back({ text, text->xmlText() });
            text->setPlainText(text->plainText());
            text->setSize(targetSize);
        });

        engraving::MeasureBase* firstBox = score->first();
        if (firstBox && firstBox->isVBox()) {
            engraving::Box* titleBox = engraving::toBox(firstBox);
            result.hasTitleFrame = true;
            result.titleFrameAutoSize = titleBox->isAutoSizeEnabled();
            result.titleFrameHeight = titleBox->boxHeight();
            result.titleFrameTopMargin = titleBox->topMargin();
            titleBox->setAutoSizeEnabled(false);
            titleBox->setBoxHeight(engraving::Spatium(DB_STUDIO_TITLE_FRAME_HEIGHT_SP));
            titleBox->setTopMargin(DB_STUDIO_PAGE_MARGIN_MM);
        }
    }

    score->setShowFrames(false);
    score->setShowInvisible(false);
    score->setShowPageborders(false);
    score->setShowUnprintable(false);

    if (config.viewMode == ViewMode::Flexible) {
        score->setShowInstrumentNames(false);
        score->setShowVBox(false);
    }

    if (config.smoothPageTransitions) {
        //! NOTE: Vertical scrolling stitches pages together; hide page headers/footers so
        //! page numbers and running text do not appear between the joined pages.
        score->style().set(engraving::Sid::showHeader, false);
        score->style().set(engraving::Sid::showFooter, false);

        if (!landscape) {
            //! 竖屏继续使用原有导出排版。横屏使用 DB Studio 的锁定排版参数。
            score->style().set(engraving::Sid::minSystemDistance, engraving::Spatium(10));
            score->style().set(engraving::Sid::maxSystemDistance, engraving::Spatium(10));

            const double pageWidth = score->style().styleD(engraving::Sid::pageWidth);
            score->style().set(engraving::Sid::pageEvenLeftMargin, 0.0);
            score->style().set(engraving::Sid::pageOddLeftMargin, 0.0);
            score->style().set(engraving::Sid::pagePrintableWidth, pageWidth);
        }
    }

    score->doLayout();

    PageList pages = notation->elements()->pages();
    if (pages.empty()) {
        LOGE() << "No pages";
        restoreScore(notation, result);
        return std::nullopt;
    }

    const Page* page = pages.front();

    if (config.viewMode == ViewMode::PageFull) {
        double scaleX = config.width / page->width();
        double scaleY = config.height / page->height();
        //! NOTE: Cover (not fit) so the page fills the whole canvas without black bars;
        //! the overflow (page margins) is cropped by the frame.
        double scale = std::max(scaleX, scaleY);
        config.canvasDpi = scale * engraving::DPI;
        config.moveToCenter = muse::PointF(0.5 * (config.width / scale - page->width()), 0.5 * (config.height / scale - page->height()));
        return result;
    }

    if (score->staves().size() > 3) {
        //! NOTE: Calculate the dpi to display all page elements
        double originalPageHeight = page->height() - score->style().styleD(engraving::Sid::pageOddTopMargin)
                                    - score->style().styleD(engraving::Sid::pageOddBottomMargin);
        double margin = 100.0;
        double ttboxHeight = originalPageHeight + margin * 2;
        double scale = config.height / ttboxHeight;
        config.canvasDpi = scale * engraving::DPI;
    }

    score->style().set(engraving::Sid::pageHeight, config.height / config.canvasDpi);
    score->style().set(engraving::Sid::pageWidth, config.width / config.canvasDpi);
    score->style().set(engraving::Sid::pagePrintableWidth, score->style().styleD(engraving::Sid::pageWidth)
                       - score->style().styleD(engraving::Sid::pageOddLeftMargin)
                       - score->style().styleD(engraving::Sid::pageEvenLeftMargin));

    if (landscape) {
        applyDbStudioLandscapeStyle(score);
    } else {
        score->style().set(engraving::Sid::pageEvenTopMargin, 0.0);
        score->style().set(engraving::Sid::pageEvenBottomMargin, 0.0);
        score->style().set(engraving::Sid::pageOddTopMargin, 0.0);
        score->style().set(engraving::Sid::pageOddBottomMargin, 0.0);
    }
    score->style().set(engraving::Sid::pageTwosided, false);
    score->style().set(engraving::Sid::showHeader, false);
    score->style().set(engraving::Sid::showFooter, false);

    if (!landscape) {
        score->style().set(engraving::Sid::minSystemDistance, engraving::Spatium(10));
        score->style().set(engraving::Sid::maxSystemDistance, engraving::Spatium(10));
        score->style().set(engraving::Sid::staffLowerBorder, engraving::Spatium(5));
        score->style().set(engraving::Sid::staffUpperBorder, engraving::Spatium(7));
    }

    score->setLayoutAll();
    score->doLayout();

    return result;
}

void VideoWriter::restoreScore(INotationPtr notation, const ScoreRestoreData& data)
{
    engraving::Score* score = notation->elements()->msScore();

    score->style() = data.style;

    score->setShowFrames(data.showFrames);
    score->setShowInstrumentNames(data.showInstrumentNames);
    score->setShowInvisible(data.showInvisible);
    score->setShowPageborders(data.showPageborders);
    score->setShowUnprintable(data.showUnprintable);
    score->setShowVBox(data.showVBox);

    if (data.hasTitleFrame) {
        engraving::MeasureBase* firstBox = score->first();
        if (firstBox && firstBox->isVBox()) {
            engraving::Box* titleBox = engraving::toBox(firstBox);
            titleBox->setAutoSizeEnabled(data.titleFrameAutoSize);
            titleBox->setBoxHeight(data.titleFrameHeight);
            titleBox->setTopMargin(data.titleFrameTopMargin);
        }
    }

    for (const ScoreRestoreData::TextRestoreData& text : data.normalizedTexts) {
        if (text.text) {
            text.text->setXmlText(text.xmlText);
        }
    }

    score->setLayoutMode(data.layoutMode);

    score->setLayoutAll();
    score->update();
}

void VideoWriter::doGenerate(muse::media::IVideoEncoderPtr encoder, INotationPtr notation, const Config& config)
{
    Config actualConfig = config;
    auto restoreData = prepareScore(notation, actualConfig);
    if (!restoreData) {
        m_writeRet = make_ret(muse::Ret::Code::UnknownError);
        m_isCompleted = true;
        return;
    }

    DEFER {
        restoreScore(notation, restoreData.value());
        m_isCompleted = true;
    };

    //! NOTE: Smooth page transitions scroll vertically through the page systems, so the
    //! page must be rendered at "fit width" scale (it may be taller than the frame) rather
    //! than the default "fit whole page" scale. This only affects the video export path.
    if (actualConfig.smoothPageTransitions && actualConfig.viewMode == ViewMode::PageFull) {
        const PageList& pages = notation->elements()->pages();
        if (!pages.empty()) {
            double scaleX = actualConfig.width / pages.front()->width();
            actualConfig.canvasDpi = scaleX * engraving::DPI;
            actualConfig.moveToCenter = muse::PointF(0.0, 0.0);
        }
    }

    // Setup painting
    QImage frame(actualConfig.width, actualConfig.height, QImage::Format_RGB32);
    frame.setDotsPerMeterX(std::lrint((actualConfig.canvasDpi * 1000) / engraving::INCH));
    frame.setDotsPerMeterY(std::lrint((actualConfig.canvasDpi * 1000) / engraving::INCH));

    QPainter qp(&frame);
    qp.setRenderHint(QPainter::Antialiasing, true);
    qp.setRenderHint(QPainter::TextAntialiasing, true);

    Painter painter(&qp, "video_writer");

    // Setup duration
    INotationPlaybackPtr playback = notation->masterNotation()->playback();
    float totalPlayTimeSec = playback->totalPlayTime();

    int leadingFrameCount = static_cast<int>(actualConfig.leadingSec * actualConfig.fps);
    int scoreFrameCount = static_cast<int>(totalPlayTimeSec * actualConfig.fps);
    int trailingFrameCount = static_cast<int>(actualConfig.trailingSec * actualConfig.fps);
    int totalFrameCount = leadingFrameCount + scoreFrameCount + trailingFrameCount;
    LOGI() << "totalPlayTime: " << totalPlayTimeSec << " sec" << " frame count " << totalFrameCount;

    m_progress.start();

    // Add score title
    if (!generateLeadingFrames(encoder, notation, painter, frame, actualConfig, totalFrameCount)) {
        return;
    }

    // Add score frames
    if (!generateScoreFrames(encoder, notation, painter, frame, actualConfig, totalPlayTimeSec, leadingFrameCount, totalFrameCount)) {
        return;
    }

    // Add trailing black frames (no "Made with MuseScore" branding)
    if (!generateTrailingFrames(encoder, painter, frame, actualConfig)) {
        return;
    }

    m_writeRet = muse::make_ok();
    m_progress.finish(muse::make_ok());
}

bool VideoWriter::generateLeadingFrames(muse::media::IVideoEncoderPtr encoder, INotationPtr notation,
                                        Painter& painter, QImage& frame,
                                        const Config& config, int totalFrameCount)
{
    int leadingFrameCount = static_cast<int>(config.leadingSec * config.fps);
    if (leadingFrameCount <= 0) {
        return true;
    }

    muse::String title = notationTitle(notation);
    muse::String subtitle = notationSubtitle(notation);

    auto scaledFontPointSize = [&config](double basePixelSize) {
        double pixelSize = basePixelSize * config.height / 1080.0;
        return pixelSize * 72.0 / engraving::DPI;
    };

    Font titleFont(Font::FontFamily(u"Muse Sans"), Font::Type::Text);
    titleFont.setPointSizeF(scaledFontPointSize(128.0));
    titleFont.setWeight(Font::Weight::Medium);

    Font subtitleFont(titleFont);
    subtitleFont.setPointSizeF(scaledFontPointSize(48.0));

    muse::RectF frameRect = muse::RectF::fromQRectF(QRectF(frame.rect()));

    const double maxTextWidth = frameRect.width() * 0.9;
    const double textLeft = (frameRect.width() - maxTextWidth) / 2.0;

    auto lineCount = [&](const FontMetrics& fm, const muse::String& text) {
        if (text.isEmpty()) {
            return 0;
        }
        double textWidth = fm.horizontalAdvance(text);
        return std::max(1, static_cast<int>(std::ceil(textWidth / maxTextWidth)));
    };

    FontMetrics titleFontMetrics(titleFont);
    const int titleLines = lineCount(titleFontMetrics, title);
    const double titleHeight = titleLines * titleFontMetrics.lineSpacing();

    FontMetrics subtitleFontMetrics(subtitleFont);
    const int subtitleLines = lineCount(subtitleFontMetrics, subtitle);
    const double subtitleHeight = subtitleLines * subtitleFontMetrics.lineSpacing();

    double centerY = frameRect.center().y();
    double titleTop = centerY - titleHeight / 2.0;
    muse::RectF titleRect(textLeft, titleTop, maxTextWidth, titleHeight);

    const double subtitleOffset = config.height / 20.0;
    double subtitleTop = titleRect.bottom() + subtitleOffset;
    muse::RectF subtitleRect(textLeft, subtitleTop, maxTextWidth, subtitleHeight);

    for (int f = 0; f < leadingFrameCount; f++) {
        if (m_abort) {
            m_writeRet = make_ret(muse::Ret::Code::Cancel);
            m_progress.finish(m_writeRet);
            return false;
        }

        m_progress.progress(f, totalFrameCount);

        painter.fillRect(frameRect, Color::BLACK);
        painter.setPen(Color::WHITE);
        painter.setFont(titleFont);
        painter.drawText(titleRect, AlignCenter, TextWordWrap, title);

        if (!subtitle.isEmpty()) {
            painter.setFont(subtitleFont);
            painter.drawText(subtitleRect, AlignCenter, TextWordWrap, subtitle);
        }

        drawWatermark(painter, frame, config);
        encoder->encodeImage(frame);
    }

    return true;
}

bool VideoWriter::generateTrailingFrames(muse::media::IVideoEncoderPtr encoder, muse::draw::Painter& painter, QImage& frame,
                                         const Config& config)
{
    int trailingFrameCount = static_cast<int>(config.trailingSec * config.fps);
    if (trailingFrameCount <= 0) {
        return true;
    }

    muse::RectF frameRect = muse::RectF::fromQRectF(QRectF(frame.rect()));

    for (int f = 0; f < trailingFrameCount; f++) {
        if (m_abort) {
            m_writeRet = make_ret(muse::Ret::Code::Cancel);
            m_progress.finish(m_writeRet);
            return false;
        }

        painter.fillRect(frameRect, Color::BLACK);
        drawWatermark(painter, frame, config);
        encoder->encodeImage(frame);
    }

    return true;
}

bool VideoWriter::generateScoreFrames(muse::media::IVideoEncoderPtr encoder, INotationPtr notation,
                                      Painter& painter, QImage& frame,
                                      const Config& config, float totalPlayTimeSec,
                                      int leadingFrameCount, int totalFrameCount)
{
    int scoreFrameCount = static_cast<int>(totalPlayTimeSec * config.fps);
    if (scoreFrameCount <= 0) {
        return true;
    }

    PageList pages = notation->elements()->pages();
    auto painting = notation->painting();
    INotationPlaybackPtr playback = notation->masterNotation()->playback();
    muse::RectF frameRect = muse::RectF::fromQRectF(QRectF(frame.rect()));

    auto pageByTick = [](const PageList& pages, tick_t tick) -> const Page* {
        for (const Page* p : pages) {
            if (tick < static_cast<tick_t>(p->endTick().ticks())) {
                return p;
            }
        }
        return nullptr;
    };

    PlaybackCursor cursor(iocContext());
    cursor.setNotation(notation);

    const bool smooth = config.smoothPageTransitions && !pages.empty();

    //! NOTE: In smooth mode, stitch pages together by their system content (uniform line
    //! spacing, no page margins) so the video reads as one continuous score.
    std::vector<double> pageRenderOffset(pages.size(), 0.0);
    std::vector<double> pageContentTop(pages.size(), 0.0);
    std::vector<double> pageContentHeight(pages.size(), 0.0);
    std::vector<System*> playbackSystems;
    std::vector<double> playbackSystemTop;
    std::vector<double> playbackSystemBottom;
    double scale = config.canvasDpi / engraving::DPI;
    double frameWidthCanvas = config.width / scale;
    double frameHeightCanvas = config.height / scale;
    double totalHeightCanvas = 0.0;
    const bool landscape = isLandscapeVideo(config.width, config.height);

    if (smooth) {
        std::vector<double> gaps;

        //! 统计页内相邻两行（跳过标题框 VBox）之间的空白间距，用于计算统一行距。
        for (size_t i = 0; i < pages.size(); ++i) {
            const std::vector<System*>& systems = pages[i]->systems();
            if (systems.empty()) {
                continue;
            }

            for (size_t k = 1; k < systems.size(); ++k) {
                if (systems[k - 1]->vbox() || systems[k]->vbox()) {
                    continue;
                }
                gaps.push_back(systems[k]->pagePos().y()
                               - (systems[k - 1]->pagePos().y() + systems[k - 1]->height()));
            }
        }

        double lineGap = 0.0;
        if (!gaps.empty()) {
            std::sort(gaps.begin(), gaps.end());
            lineGap = gaps[gaps.size() / 2];
        }

        const engraving::Score* score = notation->elements()->msScore();
        const double titleGap = landscape
                                ? score->style().styleAbsolute(engraving::Sid::frameSystemDistance)
                                : lineGap;
        if (landscape) {
            lineGap = score->style().styleAbsolute(engraving::Sid::minSystemDistance);
        }

        //! 横屏沿用 DB Studio 的上下 5 mm 边距；底部额外预留谱表下边界，
        //! 避免最后一行的谱线被视频画布裁切。
        const double layoutTopMargin = dbStudioPageMarginInches();
        const double topMargin = landscape ? layoutTopMargin : 0.0;
        const double bottomMargin = landscape
                                    ? layoutTopMargin
                                    + score->style().styleAbsolute(engraving::Sid::staffLowerBorder)
                                    : (lineGap > 0.0 ? lineGap : frameHeightCanvas * 0.08);

        //! 强制统一每一行的上下间距：直接把每个 System 的 Y 坐标重排成「统一行距」。
        //! 这样页内、以及上一页末行到下一页首行，都用同一个 gap，彻底消除翻页处变宽、
        //! 以及内容轮廓把个别行距撑开的问题（16:9 与 9:16 都适用）。
        for (size_t i = 0; i < pages.size(); ++i) {
            Page* p = pages[i];
            const std::vector<System*>& systems = p->systems();
            if (systems.empty()) {
                continue;
            }

            if (landscape) {
                //! System 的 bbox 包含标题、重音、手法和高低音谱线等实际可见内容，
                //! 而 pos.y()/height() 只是系统几何基准。横屏播放必须按可见 bbox
                //! 定位，否则标题会贴顶，最后一行的谱线也会落到画面之外。
                System* previous = nullptr;
                muse::RectF previousVisibleBox;
                for (System* s : systems) {
                    const double visibleTop = previous
                                              ? previousVisibleBox.bottom() + (previous->vbox() ? titleGap : lineGap)
                                              : topMargin;
                    const muse::RectF currentVisibleBox = visibleSystemBoundingBox(s);
                    s->setPos(s->pos().x(), s->pos().y() + visibleTop - currentVisibleBox.y());
                    previous = s;
                    previousVisibleBox = visibleSystemBoundingBox(s);
                }
                continue;
            }

            double y = systems.front()->pos().y();
            System* previous = nullptr;
            for (System* s : systems) {
                if (previous) {
                    y = previous->pos().y() + previous->height() + lineGap;
                }
                s->setPos(s->pos().x(), y);
                previous = s;
            }
        }

        std::vector<double> contentTop(pages.size(), 0.0);
        std::vector<double> contentBottom(pages.size(), 0.0);
        for (size_t i = 0; i < pages.size(); ++i) {
            const std::vector<System*>& systems = pages[i]->systems();
            if (systems.empty()) {
                continue;
            }
            if (landscape) {
                contentTop[i] = visibleSystemBoundingBox(systems.front()).y();
                contentBottom[i] = visibleSystemBoundingBox(systems.back()).bottom();
            } else {
                contentTop[i] = systems.front()->pagePos().y();
                contentBottom[i] = systems.back()->pagePos().y() + systems.back()->height();
            }
        }

        double y = topMargin;
        for (size_t i = 0; i < pages.size(); ++i) {
            if (pages[i]->systems().empty()) {
                pageRenderOffset[i] = y;
                pageContentTop[i] = y;
                pageContentHeight[i] = 0.0;
                continue;
            }

            pageRenderOffset[i] = y - contentTop[i];
            pageContentTop[i] = y;
            pageContentHeight[i] = contentBottom[i] - contentTop[i];

            y += pageContentHeight[i] + lineGap;
        }

        totalHeightCanvas = y - lineGap + bottomMargin;

        for (size_t i = 0; i < pages.size(); ++i) {
            for (System* system : pages[i]->systems()) {
                playbackSystems.push_back(system);
                const muse::RectF systemRect = visibleSystemBoundingBox(system);
                playbackSystemTop.push_back(
                    pageRenderOffset[i] + (systemRect.top() - pages[i]->pos().y()));
                playbackSystemBottom.push_back(
                    pageRenderOffset[i] + (systemRect.bottom() - pages[i]->pos().y()));
            }
        }
    }

    //! NOTE: Do NOT wrap paintPrint in save()/restore(); paintPrint installs the page
    //! viewport/window transform, and restore() would undo it, breaking the cursor draw.
    auto paintPageAt = [&](const Page* page, double offsetX, double offsetY) {
        INotationPainting::Options opt;
        opt.fromPage = static_cast<int>(page->pageNumber());
        opt.toPage = opt.fromPage;
        opt.deviceDpi = config.canvasDpi;
        opt.printPageBackground = !smooth;

        painter.translate(offsetX, offsetY);
        painting->paintPrint(&painter, opt);
        painter.translate(-offsetX, -offsetY);
    };

    auto playbackPage = [&pageByTick, &pages](tick_t tick) -> const Page* {
        const Page* page = pageByTick(pages, tick);
        return page ? page : pages.back();
    };

    auto targetViewTop = [&](const Page* page, const muse::RectF& cursorRect) {
        if (totalHeightCanvas <= frameHeightCanvas) {
            //! Landscape video starts at the DB Studio 5 mm top margin. Portrait
            //! keeps the original centred layout.
            return landscape ? 0.0 : (totalHeightCanvas - frameHeightCanvas) * 0.5;
        }

        const int pageIdx = static_cast<int>(page->pageNumber());
        const double cursorCenterY = pageRenderOffset[pageIdx]
                                     + (cursorRect.center().y() - page->pos().y());
        return std::clamp(
            cursorCenterY - frameHeightCanvas * 0.5,
            0.0,
            totalHeightCanvas - frameHeightCanvas);
    };

    auto systemIndexAt = [&](double cursorCenterY) {
        for (size_t i = 0; i < playbackSystems.size(); ++i) {
            if (cursorCenterY >= playbackSystemTop[i]
                    && cursorCenterY <= playbackSystemBottom[i]) {
                return static_cast<int>(i);
            }
        }
        return -1;
    };

    auto measureOrdinalAt = [](const System* system, tick_t playbackTick) {
        const Fraction tick = Fraction::fromTicks(playbackTick);
        int ordinal = 0;
        for (const engraving::MeasureBase* measure : system->measures()) {
            if (!measure->isMeasure()) {
                continue;
            }
            ++ordinal;
            if (tick >= measure->tick() && tick < measure->endTick()) {
                return ordinal;
            }
        }
        return ordinal;
    };

    double viewTop = 0.0;
    bool playbackFollowInitialised = false;
    int playbackFollowSystemIndex = -1;
    bool playbackFollowScrollActive = false;
    double playbackFollowTargetTop = 0.0;
    double nextPlaybackFollowUpdate = 0.0;

    for (int f = 0; f < scoreFrameCount; f++) {
        if (m_abort) {
            m_writeRet = make_ret(muse::Ret::Code::Cancel);
            m_progress.finish(m_writeRet);
            return false;
        }

        m_progress.progress(leadingFrameCount + f, totalFrameCount);

        float currentTimeSec = static_cast<float>(f) / config.fps;
        if (currentTimeSec > totalPlayTimeSec) {
            currentTimeSec = totalPlayTimeSec;
        }

        tick_t tick = playback->secToTick(currentTimeSec);

        //! DB Studio follows the cursor with a precise 8 ms timer and an
        //! interpolation factor of 0.14. Reproduce that timeline inside the
        //! export instead of snapping the viewport to every video frame.
        while (nextPlaybackFollowUpdate <= currentTimeSec + 1e-9) {
            const tick_t followTick = playback->secToTick(nextPlaybackFollowUpdate);
            const Page* followPage = playbackPage(followTick);
            if (followPage->firstMeasure()) {
                cursor.move(followTick);
                const muse::RectF followCursorRect = cursor.rect();
                const int pageIdx = static_cast<int>(followPage->pageNumber());
                const double cursorCenterY = pageRenderOffset[pageIdx]
                                             + (followCursorRect.center().y() - followPage->pos().y());
                const bool cursorVisible = cursorCenterY >= viewTop
                                           && cursorCenterY <= viewTop + frameHeightCanvas;
                const int systemIndex = systemIndexAt(cursorCenterY);

                // DB player moves the score when playback reaches the third
                // measure of the third system. After that, it repeats every two
                // systems. An explicit jump outside the viewport is always followed.
                bool shouldRetargetView = !playbackFollowInitialised
                                          || systemIndex < 0
                                          || playbackFollowSystemIndex < 0
                                          || systemIndex < playbackFollowSystemIndex
                                          || !cursorVisible;
                bool regularBlockScroll = false;
                if (!shouldRetargetView) {
                    const int systemsAdvanced = systemIndex - playbackFollowSystemIndex;
                    const int measureOrdinal =
                        systemIndex < static_cast<int>(playbackSystems.size())
                        ? measureOrdinalAt(playbackSystems[systemIndex], followTick)
                        : -1;
                    regularBlockScroll = systemsAdvanced
                                         >= DB_STUDIO_PLAYBACK_SCROLL_SYSTEM_INTERVAL
                                         && (systemsAdvanced
                                             > DB_STUDIO_PLAYBACK_SCROLL_SYSTEM_INTERVAL
                                             || measureOrdinal <= 0
                                             || measureOrdinal >= DB_STUDIO_PLAYBACK_TRIGGER_MEASURE);
                    shouldRetargetView = regularBlockScroll;
                }

                if (shouldRetargetView) {
                    playbackFollowSystemIndex = systemIndex;
                    playbackFollowScrollActive = true;
                    playbackFollowTargetTop = targetViewTop(followPage, followCursorRect);

                    if (regularBlockScroll && systemIndex > 0
                            && systemIndex < static_cast<int>(playbackSystems.size())) {
                        const double extraDistance = DB_STUDIO_PLAYBACK_EXTRA_DISTANCE_SP
                                                     * notation->elements()->msScore()->style().spatium();
                        playbackFollowTargetTop += extraDistance;

                        playbackFollowTargetTop = std::min(
                            playbackFollowTargetTop,
                            playbackSystemTop[systemIndex - 1]);
                    }
                }

                if (playbackFollowScrollActive) {
                    if (!playbackFollowInitialised) {
                        viewTop = playbackFollowTargetTop;
                        playbackFollowInitialised = true;
                        playbackFollowScrollActive = false;
                    } else if (std::abs(playbackFollowTargetTop - viewTop)
                               < DB_STUDIO_PLAYBACK_FOLLOW_EPSILON) {
                        viewTop = playbackFollowTargetTop;
                        playbackFollowScrollActive = false;
                    } else {
                        viewTop += (playbackFollowTargetTop - viewTop)
                                   * DB_STUDIO_PLAYBACK_FOLLOW_INTERPOLATION;
                    }
                }
            }
            nextPlaybackFollowUpdate += DB_STUDIO_PLAYBACK_FOLLOW_INTERVAL_SEC;
        }

        const Page* page = playbackPage(tick);
        if (!page->firstMeasure()) {
            // Skip pages with no notation
            continue;
        }

        painter.fillRect(frameRect, smooth ? Color::WHITE : Color::BLACK);

        painter.save();

        if (smooth) {
            cursor.move(tick);
            muse::RectF cursorRect = cursor.rect();

            const int pageIdx = static_cast<int>(page->pageNumber());
            const double cursorVertY = pageRenderOffset[pageIdx]
                                       + (cursorRect.y() - page->pos().y());

            //! NOTE: Render every page intersecting the vertical viewport (one page normally,
            //! two while crossing a page boundary), shifted up by the scroll offset.
            painter.translate(0.0, -viewTop);
            for (size_t i = 0; i < pages.size(); ++i) {
                const Page* p = pages[i];
                double pageTop = pageContentTop[i];
                double pageBottom = pageTop + pageContentHeight[i];
                if (pageBottom < viewTop || pageTop > viewTop + frameHeightCanvas) {
                    continue;
                }
                double centeringX = 0.5 * (frameWidthCanvas - p->width());
                paintPageAt(p, centeringX, pageRenderOffset[i]);
            }

            double cursorCenteringX = 0.5 * (frameWidthCanvas - page->width());
            muse::RectF cursorDrawRect(cursorCenteringX + (cursorRect.x() - page->pos().x()),
                                       cursorVertY,
                                       cursorRect.width(), cursorRect.height());
            painter.fillRect(cursorDrawRect, cursor.effectiveColor());
        } else {
            painter.translate(config.moveToCenter);
            paintPageAt(page, 0.0, 0.0);

            cursor.move(tick);
            muse::RectF cursorRect = cursor.rect().translated(-page->pos());
            painter.fillRect(cursorRect, cursor.effectiveColor());
        }

        painter.restore();

        drawWatermark(painter, frame, config);
        encoder->encodeImage(frame);
    }

    return true;
}

void VideoWriter::drawWatermark(muse::draw::Painter& painter, QImage& frame, const Config& config)
{
    if (!authorization() || authorization()->hasProAccess()) {
        return;
    }

    muse::RectF frameRect = muse::RectF::fromQRectF(QRectF(frame.rect()));

    const double basePixelSize = 28.0;
    const double pixelSize = basePixelSize * config.height / 1080.0;
    const double pointSize = pixelSize * 72.0 / engraving::DPI;

    Font font(Font::FontFamily(u"Muse Sans"), Font::Type::Text);
    font.setPointSizeF(pointSize);
    font.setWeight(Font::Weight::Medium);

    const double margin = frameRect.width() * 0.02;
    muse::RectF textRect(0.0, frameRect.height() - pixelSize * 2.0 - margin,
                         frameRect.width() - margin, pixelSize * 2.0);

    painter.save();
    painter.setFont(font);
    painter.setPen(Color(255, 255, 255, 120));
    painter.drawText(textRect, AlignRight | AlignBottom, TextDontClip, u"鼓乐熊AI · DB Score");
    painter.restore();
}
