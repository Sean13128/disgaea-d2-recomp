/* D2 has no PSN transport. Reject online work before returning a fake
 * transaction/context ID or leaving asynchronous result buffers untouched.
 * NIDs and error values verified against RPCS3's sceNp/sceNpTus modules. */
#include "ppu_recomp.h"
#include <cstdio>
#include <cstdint>

extern "C" void ps3_hle_register_ctx(uint32_t nid, const char* name, void (*fn)(ppu_context*));

static constexpr uint32_t NP_OFFLINE = 0x8002AA0C;
static constexpr uint32_t COMMUNITY_NO_LOGIN = 0x8002A106;

static void np_offline(ppu_context* ctx) { ctx->gpr[3] = NP_OFFLINE; }
static void community_offline(ppu_context* ctx) { ctx->gpr[3] = COMMUNITY_NO_LOGIN; }

/* Poll/Wait take (transactionId, result*). Complete with an offline failure,
 * including the out-result, so a caller cannot spin on a fabricated success. */
static void community_poll_offline(ppu_context* ctx)
{
    uint32_t result = (uint32_t)ctx->gpr[4];
    if (result) vm_write32(result, COMMUNITY_NO_LOGIN);
    ctx->gpr[3] = COMMUNITY_NO_LOGIN;
}

extern "C" void d2_register_psn_offline(void)
{
    ps3_hle_register_ctx(0x05D65DFFu, "sceNpScoreGetRankingByNpId", community_offline);
    ps3_hle_register_ctx(0x1A2704F7u, "sceNpScoreWaitAsync", community_poll_offline);
    ps3_hle_register_ctx(0x21206642u, "sceNpScoreGetRankingByRangeAsync", community_offline);
    ps3_hle_register_ctx(0x259113B8u, "sceNpScoreDestroyTitleCtx", community_offline);
    ps3_hle_register_ctx(0x2706EAA1u, "sceNpScoreSetPlayerCharacterId", community_offline);
    ps3_hle_register_ctx(0x29DD45DCu, "sceNpScoreSetTimeout", community_offline);
    ps3_hle_register_ctx(0x3DB7914Du, "sceNpScoreGetRankingByNpIdAsync", community_offline);
    ps3_hle_register_ctx(0x4026EAC5u, "sceNpBasicRegisterContextSensitiveHandler", np_offline);
    ps3_hle_register_ctx(0x5DE61626u, "sceNpLookupDestroyTitleCtx", community_offline);
    ps3_hle_register_ctx(0x5F2D9257u, "sceNpLookupInit", community_offline);
    ps3_hle_register_ctx(0x6EE62ED2u, "sceNpManagerGetContentRatingFlag", np_offline);
    ps3_hle_register_ctx(0x6F5E8143u, "sceNpScoreCreateTransactionCtx", community_offline);
    ps3_hle_register_ctx(0x7508112Eu, "sceNpLookupPollAsync", community_poll_offline);
    ps3_hle_register_ctx(0x7BE47E61u, "sceNpScoreCensorCommentAsync", community_offline);
    ps3_hle_register_ctx(0x8440537Cu, "sceNpLookupTerm", community_offline);
    ps3_hle_register_ctx(0xA1709ABDu, "sceNpManagerGetEntitlementById", np_offline);
    ps3_hle_register_ctx(0xA7A090E5u, "sceNpScorePollAsync", community_poll_offline);
    ps3_hle_register_ctx(0xB9F93BBBu, "sceNpScoreCreateTitleCtx", community_offline);
    ps3_hle_register_ctx(0xBCDBB2ABu, "sceNpBasicAddPlayersHistoryAsync", np_offline);
    ps3_hle_register_ctx(0xBDC07FD5u, "sceNpManagerGetNetworkTime", np_offline);
    ps3_hle_register_ctx(0xC4B6CD8Fu, "sceNpScoreGetRankingByNpIdPcIdAsync", community_offline);
    ps3_hle_register_ctx(0xC5F4CF82u, "sceNpScoreDestroyTransactionCtx", community_offline);
    ps3_hle_register_ctx(0xCE81C7F0u, "sceNpLookupCreateTitleCtx", community_offline);
    ps3_hle_register_ctx(0xD12E40AEu, "sceNpLookupNpIdAsync", community_offline);
    ps3_hle_register_ctx(0xDB2E4DC2u, "sceNpScoreGetGameDataAsync", community_offline);
    ps3_hle_register_ctx(0xDDCE7D15u, "sceNpScoreGetBoardInfoAsync", community_offline);
    ps3_hle_register_ctx(0xEA2E9FFCu, "sceNpLookupCreateTransactionCtx", community_offline);
    ps3_hle_register_ctx(0xEB7A3D84u, "sceNpManagerGetChatRestrictionFlag", np_offline);
    ps3_hle_register_ctx(0xF0B1E399u, "sceNpScoreRecordScoreAsync", community_offline);
    ps3_hle_register_ctx(0xF76847C2u, "sceNpScoreRecordGameDataAsync", community_offline);
    ps3_hle_register_ctx(0xFB87CF5Eu, "sceNpLookupDestroyTransactionCtx", community_offline);
    ps3_hle_register_ctx(0xFBC82301u, "sceNpScoreGetRankingByRange", community_offline);
    ps3_hle_register_ctx(0x065B610Du, "sceNpTusSetMultiSlotVariableAsync", community_offline);
    ps3_hle_register_ctx(0x0835DEB2u, "sceNpTusSetDataVUser", community_offline);
    ps3_hle_register_ctx(0x17DB7AA7u, "sceNpTusTryAndSetVariableVUserAsync", community_offline);
    ps3_hle_register_ctx(0x1904435Eu, "sceNpTusCreateTransactionCtx", community_offline);
    ps3_hle_register_ctx(0x1FA5C87Du, "sceNpTusAddAndGetVariableAsync", community_offline);
    ps3_hle_register_ctx(0x2AB21EA9u, "sceNpTusGetMultiSlotDataStatusVUserAsync", community_offline);
    ps3_hle_register_ctx(0x3175AF23u, "sceNpTusDeleteMultiSlotDataAsync", community_offline);
    ps3_hle_register_ctx(0x325C6284u, "sceNpTusAbortTransaction", community_offline);
    ps3_hle_register_ctx(0x44ECA8B4u, "sceNpTusDestroyTransactionCtx", community_offline);
    ps3_hle_register_ctx(0x651FD79Fu, "sceNpTusGetMultiSlotDataStatusAsync", community_offline);
    ps3_hle_register_ctx(0x7CAF58EEu, "sceNpTusCreateTitleCtx", community_offline);
    ps3_hle_register_ctx(0x9549D22Cu, "sceNpTusGetMultiUserVariableVUserAsync", community_offline);
    ps3_hle_register_ctx(0x96A06212u, "sceNpTusSetMultiSlotVariableVUserAsync", community_offline);
    ps3_hle_register_ctx(0xA7993BF3u, "sceNpTusAddAndGetVariableVUserAsync", community_offline);
    ps3_hle_register_ctx(0xAE4E590Eu, "sceNpTusGetDataVUser", community_offline);
    ps3_hle_register_ctx(0xBB2877F2u, "sceNpTusGetMultiSlotVariableAsync", community_offline);
    ps3_hle_register_ctx(0xBBB244B7u, "sceNpTusTryAndSetVariableAsync", community_offline);
    ps3_hle_register_ctx(0xC2E18DA8u, "sceNpTusDeleteMultiSlotVariableVUserAsync", community_offline);
    ps3_hle_register_ctx(0xC815B219u, "sceNpTusDeleteMultiSlotDataVUserAsync", community_offline);
    ps3_hle_register_ctx(0xCC7A31CDu, "sceNpTusGetMultiUserVariableAsync", community_offline);
    ps3_hle_register_ctx(0xF5363608u, "sceNpTusDeleteMultiSlotVariableAsync", community_offline);
    ps3_hle_register_ctx(0xFC7D346Eu, "sceNpTusGetMultiSlotVariableVUserAsync", community_offline);
    ps3_hle_register_ctx(0x41251F74u, "sceNp2Init", np_offline);
    ps3_hle_register_ctx(0x7D5F0F0Eu, "sceNpTusSetData", community_offline);
    ps3_hle_register_ctx(0x8DDD0D85u, "sceNpTusGetData", community_offline);
    ps3_hle_register_ctx(0x19BCE18Cu, "sceNpTusPollAsync", community_poll_offline);
    ps3_hle_register_ctx(0xB8E8FF22u, "sceNpTusWaitAsync", community_poll_offline);
    std::printf("[d2] Registered 59 PSN-offline handlers (NP=0x8002AA0C, community=0x8002A106)\n");
}
