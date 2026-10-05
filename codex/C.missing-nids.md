# D2 missing NID inventory (Task C)

All 305 entries in `port/out/imports_named.json` compared with `port/build-c/ppu_hle_nids.cpp`, plus the SDK context registrations and D2 offline handlers. RPCS3 export names resolve unnamed imports. All remaining missing imports are named.

The generated generic table alone omits **116 imports**. Of these, **23** are already served by SDK context handlers and **57** are now served by D2 offline handlers; **36** remain unresolved. The additional four TUS overrides replace existing generic handlers to reject cloud access.

Priorities describe likely impact when reached; none of these 36 imports was observed unresolved during the verified 40-second boot.

## P1 — graphics synchronization, filesystem and module loading (10)

| Library | NID | Function |
|---|---|---|
| cellResc | `0x0D3C22CE` | cellRescSetWaitFlip |
| cellGcmSys | `0x3A33C1FD` | _cellGcmFunc15 |
| sys_fs | `0x4CEF342E` | cellFsAioWrite |
| sys_fs | `0x6D3BB15B` | cellFsSdataOpenByFd |
| sysPrxForUser | `0x26090058` | sys_prx_load_module |
| sysPrxForUser | `0x42B23552` | sys_prx_register_library |
| sysPrxForUser | `0xA330AD84` | sys_prx_load_module_on_memcontainer_by_fd |
| sysPrxForUser | `0xAA6D9BFF` | sys_prx_load_module_on_memcontainer |
| sysPrxForUser | `0xE0DA8EFD` | sys_spu_image_close |
| sysPrxForUser | `0xEF68C17C` | sys_prx_load_module_by_fd |

## P2 — media playback, text conversion, clock, content and error UI (20)

| Library | NID | Function |
|---|---|---|
| cellSysutil | `0x3E22CB4B` | cellMsgDialogOpenErrorCode |
| cellL10n | `0x33435818` | SJISstoUTF8s |
| cellL10n | `0x750C363D` | jstrchk |
| cellL10n | `0xDD5EBDEB` | UTF8stoSJISs |
| cellVpost | `0x10EF39F6` | cellVpostClose |
| cellVpost | `0x95E788C3` | cellVpostQueryAttr |
| cellVpost | `0xCD33F3E2` | cellVpostOpen |
| cellDmux | `0x02170D1A` | cellDmuxQueryEsAttr |
| cellDmux | `0xA2D4189B` | cellDmuxQueryAttr |
| cellPamf | `0x28B4E2C1` | cellPamfReaderSetStreamWithTypeAndIndex |
| cellPamf | `0x44F5C9E3` | cellPamfGetStreamOffsetAndSize |
| cellPamf | `0x9AB20793` | cellPamfReaderGetStreamTypeAndChannel |
| cellPamf | `0xCA8181C1` | cellPamfGetHeaderSize |
| cellAtrac | `0x2BFFF084` | cellAtracGetStreamDataInfo |
| cellAtrac | `0x46CFC013` | cellAtracAddStreamData |
| cellAtrac | `0x99EFE171` | cellAtracIsSecondBufferNeeded |
| cellAtrac | `0x99FB73D1` | cellAtracGetBufferInfoForResetting |
| cellRtc | `0x269A1882` | cellRtcTickAddTicks |
| cellGameExec | `0x59B1EDE1` | cellGameGetHomeDataExportPath |
| cellGame | `0xCE4374F6` | cellGamePatchCheck |

## P3 — optional local trophy, keyboard and offline network paths (6)

| Library | NID | Function |
|---|---|---|
| sys_io | `0xFF0A21B7` | cellKbRead |
| sys_net | `0x28E208BB` | listen |
| sys_net | `0xA50777C6` | shutdown |
| sys_net | `0xC94F6939` | accept |
| sys_net | `0xDC751B40` | send |
| sceNpTrophy | `0x48BD97C7` | sceNpTrophyAbortHandle |

## Complete generated-table omission audit

This includes imports resolved outside the generated generic table, to avoid reporting working context handlers as missing.

| Library | NID | Function | Resolution |
|---|---|---|---|
| sys_io | `0xFF0A21B7` | cellKbRead | Missing (see priorities above) |
| cellResc | `0x0D3C22CE` | cellRescSetWaitFlip | Missing (see priorities above) |
| cellGcmSys | `0x15BAE46B` | _cellGcmInitBody | SDK context handler |
| cellGcmSys | `0x3A33C1FD` | _cellGcmFunc15 | Missing (see priorities above) |
| cellSysutil | `0x3E22CB4B` | cellMsgDialogOpenErrorCode | Missing (see priorities above) |
| sys_fs | `0x2796FDF3` | cellFsRmdir | SDK context handler |
| sys_fs | `0x4CEF342E` | cellFsAioWrite | Missing (see priorities above) |
| sys_fs | `0x9F951810` | cellFsAioFinish | SDK context handler |
| sys_fs | `0xC1C507E7` | cellFsAioRead | SDK context handler |
| sys_fs | `0xDB869F20` | cellFsAioInit | SDK context handler |
| sys_fs | `0x6D3BB15B` | cellFsSdataOpenByFd | Missing (see priorities above) |
| sys_fs | `0x967A162B` | cellFsFsync | SDK context handler |
| sys_fs | `0xB1840B53` | cellFsSdataOpen | SDK context handler |
| cellL10n | `0x33435818` | SJISstoUTF8s | Missing (see priorities above) |
| cellL10n | `0x750C363D` | jstrchk | Missing (see priorities above) |
| cellL10n | `0xDD5EBDEB` | UTF8stoSJISs | Missing (see priorities above) |
| sys_net | `0x28E208BB` | listen | Missing (see priorities above) |
| sys_net | `0x3F09E20A` | sys_net_bnet_select (SDK label) | SDK context handler |
| sys_net | `0x6005CDE1` | _sys_net_errno_loc | SDK context handler |
| sys_net | `0x6DB6E8CD` | socketclose | SDK context handler |
| sys_net | `0x9C056962` | socket | SDK context handler |
| sys_net | `0xA50777C6` | shutdown | Missing (see priorities above) |
| sys_net | `0xB0A59804` | bind | SDK context handler |
| sys_net | `0xC94F6939` | accept | Missing (see priorities above) |
| sys_net | `0xDC751B40` | send | Missing (see priorities above) |
| sys_net | `0xFBA04F37` | recv | SDK context handler |
| sys_net | `0xFDB8F926` | sys_net_free_thread_context | SDK context handler |
| cellVpost | `0x10EF39F6` | cellVpostClose | Missing (see priorities above) |
| cellVpost | `0x95E788C3` | cellVpostQueryAttr | Missing (see priorities above) |
| cellVpost | `0xCD33F3E2` | cellVpostOpen | Missing (see priorities above) |
| cellDmux | `0x02170D1A` | cellDmuxQueryEsAttr | Missing (see priorities above) |
| cellDmux | `0xA2D4189B` | cellDmuxQueryAttr | Missing (see priorities above) |
| cellPamf | `0x28B4E2C1` | cellPamfReaderSetStreamWithTypeAndIndex | Missing (see priorities above) |
| cellPamf | `0x44F5C9E3` | cellPamfGetStreamOffsetAndSize | Missing (see priorities above) |
| cellPamf | `0x9AB20793` | cellPamfReaderGetStreamTypeAndChannel | Missing (see priorities above) |
| cellPamf | `0xCA8181C1` | cellPamfGetHeaderSize | Missing (see priorities above) |
| cellAtrac | `0x2BFFF084` | cellAtracGetStreamDataInfo | Missing (see priorities above) |
| cellAtrac | `0x46CFC013` | cellAtracAddStreamData | Missing (see priorities above) |
| cellAtrac | `0x99EFE171` | cellAtracIsSecondBufferNeeded | Missing (see priorities above) |
| cellAtrac | `0x99FB73D1` | cellAtracGetBufferInfoForResetting | Missing (see priorities above) |
| sceNp | `0x05D65DFF` | sceNpScoreGetRankingByNpId | D2 PSN-offline handler |
| sceNp | `0x1A2704F7` | sceNpScoreWaitAsync | D2 PSN-offline handler |
| sceNp | `0x21206642` | sceNpScoreGetRankingByRangeAsync | D2 PSN-offline handler |
| sceNp | `0x259113B8` | sceNpScoreDestroyTitleCtx | D2 PSN-offline handler |
| sceNp | `0x2706EAA1` | sceNpScoreSetPlayerCharacterId | D2 PSN-offline handler |
| sceNp | `0x29DD45DC` | sceNpScoreSetTimeout | D2 PSN-offline handler |
| sceNp | `0x3DB7914D` | sceNpScoreGetRankingByNpIdAsync | D2 PSN-offline handler |
| sceNp | `0x4026EAC5` | sceNpBasicRegisterContextSensitiveHandler | D2 PSN-offline handler |
| sceNp | `0x5DE61626` | sceNpLookupDestroyTitleCtx | D2 PSN-offline handler |
| sceNp | `0x5F2D9257` | sceNpLookupInit | D2 PSN-offline handler |
| sceNp | `0x6EE62ED2` | sceNpManagerGetContentRatingFlag | D2 PSN-offline handler |
| sceNp | `0x6F5E8143` | sceNpScoreCreateTransactionCtx | D2 PSN-offline handler |
| sceNp | `0x7508112E` | sceNpLookupPollAsync | D2 PSN-offline handler |
| sceNp | `0x7BE47E61` | sceNpScoreCensorCommentAsync | D2 PSN-offline handler |
| sceNp | `0x8440537C` | sceNpLookupTerm | D2 PSN-offline handler |
| sceNp | `0xA1709ABD` | sceNpManagerGetEntitlementById | D2 PSN-offline handler |
| sceNp | `0xA7A090E5` | sceNpScorePollAsync | D2 PSN-offline handler |
| sceNp | `0xAD218FAF` | sceNpDrmIsAvailable | D2 PSN-offline handler |
| sceNp | `0xB9F93BBB` | sceNpScoreCreateTitleCtx | D2 PSN-offline handler |
| sceNp | `0xBCDBB2AB` | sceNpBasicAddPlayersHistoryAsync | D2 PSN-offline handler |
| sceNp | `0xBDC07FD5` | sceNpManagerGetNetworkTime | D2 PSN-offline handler |
| sceNp | `0xC4B6CD8F` | sceNpScoreGetRankingByNpIdPcIdAsync | D2 PSN-offline handler |
| sceNp | `0xC5F4CF82` | sceNpScoreDestroyTransactionCtx | D2 PSN-offline handler |
| sceNp | `0xCE81C7F0` | sceNpLookupCreateTitleCtx | D2 PSN-offline handler |
| sceNp | `0xD12E40AE` | sceNpLookupNpIdAsync | D2 PSN-offline handler |
| sceNp | `0xDB2E4DC2` | sceNpScoreGetGameDataAsync | D2 PSN-offline handler |
| sceNp | `0xDDCE7D15` | sceNpScoreGetBoardInfoAsync | D2 PSN-offline handler |
| sceNp | `0xEA2E9FFC` | sceNpLookupCreateTransactionCtx | D2 PSN-offline handler |
| sceNp | `0xEB7A3D84` | sceNpManagerGetChatRestrictionFlag | D2 PSN-offline handler |
| sceNp | `0xF0B1E399` | sceNpScoreRecordScoreAsync | D2 PSN-offline handler |
| sceNp | `0xF76847C2` | sceNpScoreRecordGameDataAsync | D2 PSN-offline handler |
| sceNp | `0xFB87CF5E` | sceNpLookupDestroyTransactionCtx | D2 PSN-offline handler |
| sceNp | `0xFBC82301` | sceNpScoreGetRankingByRange | D2 PSN-offline handler |
| sceNp | `0xF042B14F` | sceNpDrmIsAvailable2 | D2 PSN-offline handler |
| cellRtc | `0x269A1882` | cellRtcTickAddTicks | Missing (see priorities above) |
| sceNpTrophy | `0x48BD97C7` | sceNpTrophyAbortHandle | Missing (see priorities above) |
| cellGameExec | `0x59B1EDE1` | cellGameGetHomeDataExportPath | Missing (see priorities above) |
| cellGame | `0xCE4374F6` | cellGamePatchCheck | Missing (see priorities above) |
| sceNpTus | `0x065B610D` | sceNpTusSetMultiSlotVariableAsync | D2 PSN-offline handler |
| sceNpTus | `0x0835DEB2` | sceNpTusSetDataVUser | D2 PSN-offline handler |
| sceNpTus | `0x17DB7AA7` | sceNpTusTryAndSetVariableVUserAsync | D2 PSN-offline handler |
| sceNpTus | `0x1904435E` | sceNpTusCreateTransactionCtx | D2 PSN-offline handler |
| sceNpTus | `0x1FA5C87D` | sceNpTusAddAndGetVariableAsync | D2 PSN-offline handler |
| sceNpTus | `0x2AB21EA9` | sceNpTusGetMultiSlotDataStatusVUserAsync | D2 PSN-offline handler |
| sceNpTus | `0x3175AF23` | sceNpTusDeleteMultiSlotDataAsync | D2 PSN-offline handler |
| sceNpTus | `0x325C6284` | sceNpTusAbortTransaction | D2 PSN-offline handler |
| sceNpTus | `0x44ECA8B4` | sceNpTusDestroyTransactionCtx | D2 PSN-offline handler |
| sceNpTus | `0x651FD79F` | sceNpTusGetMultiSlotDataStatusAsync | D2 PSN-offline handler |
| sceNpTus | `0x7CAF58EE` | sceNpTusCreateTitleCtx | D2 PSN-offline handler |
| sceNpTus | `0x9549D22C` | sceNpTusGetMultiUserVariableVUserAsync | D2 PSN-offline handler |
| sceNpTus | `0x96A06212` | sceNpTusSetMultiSlotVariableVUserAsync | D2 PSN-offline handler |
| sceNpTus | `0xA7993BF3` | sceNpTusAddAndGetVariableVUserAsync | D2 PSN-offline handler |
| sceNpTus | `0xAE4E590E` | sceNpTusGetDataVUser | D2 PSN-offline handler |
| sceNpTus | `0xBB2877F2` | sceNpTusGetMultiSlotVariableAsync | D2 PSN-offline handler |
| sceNpTus | `0xBBB244B7` | sceNpTusTryAndSetVariableAsync | D2 PSN-offline handler |
| sceNpTus | `0xC2E18DA8` | sceNpTusDeleteMultiSlotVariableVUserAsync | D2 PSN-offline handler |
| sceNpTus | `0xC815B219` | sceNpTusDeleteMultiSlotDataVUserAsync | D2 PSN-offline handler |
| sceNpTus | `0xCC7A31CD` | sceNpTusGetMultiUserVariableAsync | D2 PSN-offline handler |
| sceNpTus | `0xF5363608` | sceNpTusDeleteMultiSlotVariableAsync | D2 PSN-offline handler |
| sceNpTus | `0xFC7D346E` | sceNpTusGetMultiSlotVariableVUserAsync | D2 PSN-offline handler |
| sceNp2 | `0x41251F74` | sceNp2Init | D2 PSN-offline handler |
| sysPrxForUser | `0x24A1EA07` | sys_ppu_thread_create | SDK context handler |
| sysPrxForUser | `0x26090058` | sys_prx_load_module | Missing (see priorities above) |
| sysPrxForUser | `0x2C847572` | _sys_process_atexitspawn | SDK context handler |
| sysPrxForUser | `0x350D454E` | sys_ppu_thread_get_id | SDK context handler |
| sysPrxForUser | `0x42B23552` | sys_prx_register_library | Missing (see priorities above) |
| sysPrxForUser | `0x4F7172C9` | sys_process_is_stack | SDK context handler |
| sysPrxForUser | `0x744680A2` | sys_initialize_tls | SDK context handler |
| sysPrxForUser | `0x8461E528` | sys_time_get_system_time | SDK context handler |
| sysPrxForUser | `0x96328741` | _sys_process_at_Exitspawn | SDK context handler |
| sysPrxForUser | `0xA330AD84` | sys_prx_load_module_on_memcontainer_by_fd | Missing (see priorities above) |
| sysPrxForUser | `0xAA6D9BFF` | sys_prx_load_module_on_memcontainer | Missing (see priorities above) |
| sysPrxForUser | `0xAFF080A4` | sys_ppu_thread_exit | SDK context handler |
| sysPrxForUser | `0xE0DA8EFD` | sys_spu_image_close | Missing (see priorities above) |
| sysPrxForUser | `0xEBE5F72F` | sys_spu_image_import | SDK context handler |
| sysPrxForUser | `0xEF68C17C` | sys_prx_load_module_by_fd | Missing (see priorities above) |

Names verified from [RPCS3 Cell modules](https://github.com/RPCS3/rpcs3/tree/master/rpcs3/Emu/Cell/Modules); SDK context coverage is read from `ppu_fs.cpp` and `ppu_sysprx.cpp`.
