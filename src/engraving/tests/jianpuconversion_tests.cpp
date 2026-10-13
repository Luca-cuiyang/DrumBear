/*
 * SPDX-License-Identifier: GPL-3.0-only
 * MuseScore-Studio-CLA-applies
 *
 * MuseScore Studio
 * Music Composition & Notation
 *
 * Copyright (C) 2021 MuseScore Limited and others
 */

#include <gtest/gtest.h>

#include "engraving/dom/pitchspelling.h"
#include "engraving/types/types.h"

using namespace mu::engraving;

class Engraving_JianpuConversionTests : public ::testing::Test
{
};

// 验证首调简谱的核心换算：数字 1-7 → 调内音级（TPC）。
// 这是「数字直输」功能的地基，必须对全调号都准确。
TEST_F(Engraving_JianpuConversionTests, digitToTpc_CMajor)
{
    // C 大调：1=C, 2=D, 3=E, 4=F, 5=G, 6=A, 7=B
    EXPECT_EQ(function2Tpc(u"1", Key::C), Tpc::TPC_C);
    EXPECT_EQ(function2Tpc(u"2", Key::C), Tpc::TPC_D);
    EXPECT_EQ(function2Tpc(u"3", Key::C), Tpc::TPC_E);
    EXPECT_EQ(function2Tpc(u"4", Key::C), Tpc::TPC_F);
    EXPECT_EQ(function2Tpc(u"5", Key::C), Tpc::TPC_G);
    EXPECT_EQ(function2Tpc(u"6", Key::C), Tpc::TPC_A);
    EXPECT_EQ(function2Tpc(u"7", Key::C), Tpc::TPC_B);
}

TEST_F(Engraving_JianpuConversionTests, digitToTpc_GMajor)
{
    // G 大调：1=G, 2=A, 3=B, 4=C, 5=D, 6=E, 7=F#
    EXPECT_EQ(function2Tpc(u"1", Key::G), Tpc::TPC_G);
    EXPECT_EQ(function2Tpc(u"2", Key::G), Tpc::TPC_A);
    EXPECT_EQ(function2Tpc(u"3", Key::G), Tpc::TPC_B);
    EXPECT_EQ(function2Tpc(u"4", Key::G), Tpc::TPC_C);
    EXPECT_EQ(function2Tpc(u"5", Key::G), Tpc::TPC_D);
    EXPECT_EQ(function2Tpc(u"6", Key::G), Tpc::TPC_E);
    EXPECT_EQ(function2Tpc(u"7", Key::G), Tpc::TPC_F_S);
}

TEST_F(Engraving_JianpuConversionTests, digitToTpc_FMajor)
{
    // F 大调：1=F, 2=G, 3=A, 4=Bb, 5=C, 6=D, 7=E
    EXPECT_EQ(function2Tpc(u"1", Key::F), Tpc::TPC_F);
    EXPECT_EQ(function2Tpc(u"2", Key::F), Tpc::TPC_G);
    EXPECT_EQ(function2Tpc(u"3", Key::F), Tpc::TPC_A);
    EXPECT_EQ(function2Tpc(u"4", Key::F), Tpc::TPC_B_B);
    EXPECT_EQ(function2Tpc(u"5", Key::F), Tpc::TPC_C);
    EXPECT_EQ(function2Tpc(u"6", Key::F), Tpc::TPC_D);
    EXPECT_EQ(function2Tpc(u"7", Key::F), Tpc::TPC_E);
}

TEST_F(Engraving_JianpuConversionTests, digitToTpc_BbMajor)
{
    // 降 B 大调：1=Bb, 2=C, 3=D, 4=Eb, 5=F, 6=G, 7=A
    EXPECT_EQ(function2Tpc(u"1", Key::B_B), Tpc::TPC_B_B);
    EXPECT_EQ(function2Tpc(u"2", Key::B_B), Tpc::TPC_C);
    EXPECT_EQ(function2Tpc(u"3", Key::B_B), Tpc::TPC_D);
    EXPECT_EQ(function2Tpc(u"4", Key::B_B), Tpc::TPC_E_B);
    EXPECT_EQ(function2Tpc(u"5", Key::B_B), Tpc::TPC_F);
    EXPECT_EQ(function2Tpc(u"6", Key::B_B), Tpc::TPC_G);
    EXPECT_EQ(function2Tpc(u"7", Key::B_B), Tpc::TPC_A);
}
