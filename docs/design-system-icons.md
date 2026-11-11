# Design system icon sources

The standalone foundations introduced in 0.4.18 are also used by the actual Java-page Material 3 controls and bottom navigation in 0.4.19.

`AppIcons` exposes one distinct Material Outlined symbol for each of the 16 entry points and four Filled variants for selected bottom navigation. The existing `material-icons-core` dependency supplies the standard auto-mirrored Back arrow. No extended icon dependency is added.

## Source and conversion

- Upstream: [Google Material Design Icons](https://github.com/google/material-design-icons/tree/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7).
- Pinned revision: `10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7`.
- License: Apache License 2.0; the upstream license is reproduced below.
- Source: official 24px SVGs, converted to local 24dp Android vector XML. Source paths are unchanged. SVG rect/circle/polygon primitives are expressed as equivalent vector paths; empty `fill="none"` bounds and structural groups are omitted. No icon geometry was designed or redrawn.
- A vector name is added for stable resource identity; black asset fills are tinted by official Compose `Icon` or Material View controls using the shared `MaterialTheme` roles.
- The source and resulting file SHA-256 hashes allow later updates to be reviewed against these exact assets.

| AppIcons property | Official source | Source SVG SHA-256 | Local vector SHA-256 |
| --- | --- | --- | --- |
| `Connections` | [src/device/devices/materialiconsoutlined/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/device/devices/materialiconsoutlined/24px.svg) | `f2bcb4382a5a9056a1669f746a3ba9dd653063a1d7e4d52f73bae9e52bda86a4` | `de36bc75cfe12fe2cf0f11ee74dee6c9a30e3428949bdc5697f9fab651952f6b` |
| `Discover` | [src/action/explore/materialiconsoutlined/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/action/explore/materialiconsoutlined/24px.svg) | `2cfc40f7f33e2fe3dc591b4ad68128e9a564e3f0c1c7edc73d0d684d4f038b1d` | `e61fa0014a8e864a97ce4995f173d82834230de3cb95eef7a9e9690c27dc2a8b` |
| `DiscoverFilled` | [src/action/explore/materialicons/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/action/explore/materialicons/24px.svg) | `5fdb65e9bc24dacac5c1e1d88c546858a8fc9e8842b744a5c306334544696d20` | `1ef4dc01a7efe459a47ca172c590e93619d63ee4495534cde345282ab5784c17` |
| `Favorite` | [src/action/favorite_border/materialiconsoutlined/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/action/favorite_border/materialiconsoutlined/24px.svg) | `347bf3193b0faa3ec5ade1cf3a8894ab7e5132e414aa4e2bdeffb01e51715b79` | `8d6e3a69f62bf6e7052284296ac3ed0cb28d58f22bcf75cc0173af1b3feff9eb` |
| `Filter` | [src/action/filter_alt/materialiconsoutlined/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/action/filter_alt/materialiconsoutlined/24px.svg) | `ecb1255c7e5dcf021adf87a47e9d28da449268a5dcea1401814e910dbcd31609` | `1777cc5ec15bebe2f06f22fa0a388f9f1dda88b018a18af27426d758988a406e` |
| `Home` | [src/action/home/materialiconsoutlined/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/action/home/materialiconsoutlined/24px.svg) | `6f5d2c85c8d60a818c3d6011e7cf1b981bc7c7ba5a7ced3664c6c0b6d42c9d69` | `1c0d0a301fbb5fc11d3acdb348b35c0e44de5f5f2af03e57a1f465de8b2f1ce0` |
| `HomeFilled` | [src/action/home/materialicons/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/action/home/materialicons/24px.svg) | `99da329970f65dbf03ce2450ac8c613caac4ca53523fd2da1be4421a49f376a3` | `d45bf365b607eb0ff993e27cea078260fb4e7ee00fe8328940e8659b4af03d7c` |
| `Library` | [src/av/video_library/materialiconsoutlined/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/av/video_library/materialiconsoutlined/24px.svg) | `be6359d47fe6dde1133a04ddd51dbad2c74c0ce9605c73bd573e5c3660e42297` | `13d35d18cf742b1d2a50c1bb2f44ca54a9488e97d58cd09e27fcc11f8ee16675` |
| `LibraryFilled` | [src/av/video_library/materialicons/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/av/video_library/materialicons/24px.svg) | `0a12cc49709b8cc83343400a0b880ba43e607828e4c152826b41a41fd42fdecc` | `2fc8557117b3efb831bfdd46e1c5db63cfc4a4db6faa99305f83958540d1c05d` |
| `Mine` | [src/social/person/materialiconsoutlined/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/social/person/materialiconsoutlined/24px.svg) | `505afee5ac41b4d8ce4d032645ec56fa0ee64c57781ad33e67a74a21cbdf5e15` | `fa94d00cea47ee97355d9f0d6aa7da006e5d0496c3344ad16e8a7ae3c0ffe037` |
| `MineFilled` | [src/social/person/materialicons/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/social/person/materialicons/24px.svg) | `b3a98217a56e54c9ec91138f1c22c0c85163407c955dfd0c8c46b9192e5667f5` | `8c76f4d36cf0aa78ee9e668d82e782f5c690c60230cbc85dc3908eecb724f9d5` |
| `More` | [src/navigation/more_vert/materialiconsoutlined/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/navigation/more_vert/materialiconsoutlined/24px.svg) | `a7ea30a533f717f1e472fab3c3547ede0ec3c27d0a1f5f36af201db59dbfe432` | `69c5684c3bffe8533c7acd8264c33c092d6cacecd55020884c7688e53f9c09b7` |
| `PhoneQueue` | [src/av/playlist_play/materialiconsoutlined/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/av/playlist_play/materialiconsoutlined/24px.svg) | `6ad4a4c323589fbf5bbbaabf1d6045c51a4377d107eeb36591aa54acea718e28` | `a7552c1571fba6e2335f1f30c77319f85c47f8153b2aa5bb7bffcac8ca89aded` |
| `Remote` | [src/action/settings_remote/materialiconsoutlined/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/action/settings_remote/materialiconsoutlined/24px.svg) | `0b933e6e42dfd8ba09de05336b5d5ab30efb1ce917df568d914d31b6cabcbd1a` | `84023d55c2c6bedf50ba521364d421939cfe9e0bb3f5cca25eda193e69c1e946` |
| `Search` | [src/action/search/materialiconsoutlined/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/action/search/materialiconsoutlined/24px.svg) | `4679a3ccd253f707eeacf7edbb2fb3e395174b690a9ca55ab5fe8a3826002625` | `4cc15fec2c23bbd24042d422004c3e80ff89efdd9e1f3fba99044c74a32774c3` |
| `SmartPlaylist` | [src/image/auto_awesome_motion/materialiconsoutlined/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/image/auto_awesome_motion/materialiconsoutlined/24px.svg) | `6a46d670de7d47c49e83b2dfb393458b3b276200263294c9e6f731a7f7230b7e` | `894d0ce2f469c5e012d2fb61b3976eecf8fe6e9b39ce2f1bf457c15db740bab7` |
| `Sort` | [src/content/sort/materialiconsoutlined/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/content/sort/materialiconsoutlined/24px.svg) | `fdd697d186aba2e98ad6f208bb48ce1c93839cf98bb6262ff951533874d0c42b` | `916bfc15c5aea09a75eff5466087e9ceee3152130ff78de29f64885f9cb2b623` |
| `Statistics` | [src/editor/bar_chart/materialiconsoutlined/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/editor/bar_chart/materialiconsoutlined/24px.svg) | `5abe3390a29d11d9a3e2e212224d5196272a9072ae8bb76c963bf18fee4d5fe1` | `7d18af64dd404ea60236afa96580c5818168dc37145a46c7bd40daa538f4d0ea` |
| `Tasks` | [src/action/assignment/materialiconsoutlined/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/action/assignment/materialiconsoutlined/24px.svg) | `374fa92bf5aec461e429335bc591f27fac552da2e1a36dfe560f795f5988f345` | `e55ba63a7fb216c8f27204da6d516cc37ae5e16214bae6d1c94b96e142affc6d` |
| `Watchlist` | [src/action/bookmark_border/materialiconsoutlined/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/action/bookmark_border/materialiconsoutlined/24px.svg) | `1a624fa82577014fbf066bd8ffd6817ea3532c34413a9810af442e7b1c78f9eb` | `f8b0270a3f4c3edd1d9d9851922cc01105ee0bde621a1fad46c2eea616808262` |

## Native action assets (0.4.19)

Selected favorite and watchlist actions use official Filled Favorite and Bookmark; unselected actions retain their outlined variants. These paths follow the same pinned upstream Material Icons source and Apache 2.0 license.

| Local vector | Official source | Local SHA-256 |
| --- | --- | --- |
| `design_system_favorite_filled` | [src/action/favorite/materialicons/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/action/favorite/materialicons/24px.svg) | `8c3d16524c01831a59464b85f2221638d9f9b42efe56d6766152fd75fe96a6ab` |
| `design_system_watchlist_filled` | [src/action/bookmark/materialicons/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/action/bookmark/materialicons/24px.svg) | `a4172cb8502c5e7003f046606de4087e21126499b491fb0f1b28d9b99d7470ae` |
| `design_system_shuffle` | [src/av/shuffle/materialicons/24px.svg](https://raw.githubusercontent.com/google/material-design-icons/10ecc14790612ca8fd164e3f4ffe9c16fc50d5b7/src/av/shuffle/materialicons/24px.svg) | `01892685b123aa675dae310e594cc43d4183ad9adadaeba1a50b9ac37fba5679` |

## Retained upstream license

```text

                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

   1. Definitions.

      "License" shall mean the terms and conditions for use, reproduction,
      and distribution as defined by Sections 1 through 9 of this document.

      "Licensor" shall mean the copyright owner or entity authorized by
      the copyright owner that is granting the License.

      "Legal Entity" shall mean the union of the acting entity and all
      other entities that control, are controlled by, or are under common
      control with that entity. For the purposes of this definition,
      "control" means (i) the power, direct or indirect, to cause the
      direction or management of such entity, whether by contract or
      otherwise, or (ii) ownership of fifty percent (50%) or more of the
      outstanding shares, or (iii) beneficial ownership of such entity.

      "You" (or "Your") shall mean an individual or Legal Entity
      exercising permissions granted by this License.

      "Source" form shall mean the preferred form for making modifications,
      including but not limited to software source code, documentation
      source, and configuration files.

      "Object" form shall mean any form resulting from mechanical
      transformation or translation of a Source form, including but
      not limited to compiled object code, generated documentation,
      and conversions to other media types.

      "Work" shall mean the work of authorship, whether in Source or
      Object form, made available under the License, as indicated by a
      copyright notice that is included in or attached to the work
      (an example is provided in the Appendix below).

      "Derivative Works" shall mean any work, whether in Source or Object
      form, that is based on (or derived from) the Work and for which the
      editorial revisions, annotations, elaborations, or other modifications
      represent, as a whole, an original work of authorship. For the purposes
      of this License, Derivative Works shall not include works that remain
      separable from, or merely link (or bind by name) to the interfaces of,
      the Work and Derivative Works thereof.

      "Contribution" shall mean any work of authorship, including
      the original version of the Work and any modifications or additions
      to that Work or Derivative Works thereof, that is intentionally
      submitted to Licensor for inclusion in the Work by the copyright owner
      or by an individual or Legal Entity authorized to submit on behalf of
      the copyright owner. For the purposes of this definition, "submitted"
      means any form of electronic, verbal, or written communication sent
      to the Licensor or its representatives, including but not limited to
      communication on electronic mailing lists, source code control systems,
      and issue tracking systems that are managed by, or on behalf of, the
      Licensor for the purpose of discussing and improving the Work, but
      excluding communication that is conspicuously marked or otherwise
      designated in writing by the copyright owner as "Not a Contribution."

      "Contributor" shall mean Licensor and any individual or Legal Entity
      on behalf of whom a Contribution has been received by Licensor and
      subsequently incorporated within the Work.

   2. Grant of Copyright License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      copyright license to reproduce, prepare Derivative Works of,
      publicly display, publicly perform, sublicense, and distribute the
      Work and such Derivative Works in Source or Object form.

   3. Grant of Patent License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      (except as stated in this section) patent license to make, have made,
      use, offer to sell, sell, import, and otherwise transfer the Work,
      where such license applies only to those patent claims licensable
      by such Contributor that are necessarily infringed by their
      Contribution(s) alone or by combination of their Contribution(s)
      with the Work to which such Contribution(s) was submitted. If You
      institute patent litigation against any entity (including a
      cross-claim or counterclaim in a lawsuit) alleging that the Work
      or a Contribution incorporated within the Work constitutes direct
      or contributory patent infringement, then any patent licenses
      granted to You under this License for that Work shall terminate
      as of the date such litigation is filed.

   4. Redistribution. You may reproduce and distribute copies of the
      Work or Derivative Works thereof in any medium, with or without
      modifications, and in Source or Object form, provided that You
      meet the following conditions:

      (a) You must give any other recipients of the Work or
          Derivative Works a copy of this License; and

      (b) You must cause any modified files to carry prominent notices
          stating that You changed the files; and

      (c) You must retain, in the Source form of any Derivative Works
          that You distribute, all copyright, patent, trademark, and
          attribution notices from the Source form of the Work,
          excluding those notices that do not pertain to any part of
          the Derivative Works; and

      (d) If the Work includes a "NOTICE" text file as part of its
          distribution, then any Derivative Works that You distribute must
          include a readable copy of the attribution notices contained
          within such NOTICE file, excluding those notices that do not
          pertain to any part of the Derivative Works, in at least one
          of the following places: within a NOTICE text file distributed
          as part of the Derivative Works; within the Source form or
          documentation, if provided along with the Derivative Works; or,
          within a display generated by the Derivative Works, if and
          wherever such third-party notices normally appear. The contents
          of the NOTICE file are for informational purposes only and
          do not modify the License. You may add Your own attribution
          notices within Derivative Works that You distribute, alongside
          or as an addendum to the NOTICE text from the Work, provided
          that such additional attribution notices cannot be construed
          as modifying the License.

      You may add Your own copyright statement to Your modifications and
      may provide additional or different license terms and conditions
      for use, reproduction, or distribution of Your modifications, or
      for any such Derivative Works as a whole, provided Your use,
      reproduction, and distribution of the Work otherwise complies with
      the conditions stated in this License.

   5. Submission of Contributions. Unless You explicitly state otherwise,
      any Contribution intentionally submitted for inclusion in the Work
      by You to the Licensor shall be under the terms and conditions of
      this License, without any additional terms or conditions.
      Notwithstanding the above, nothing herein shall supersede or modify
      the terms of any separate license agreement you may have executed
      with Licensor regarding such Contributions.

   6. Trademarks. This License does not grant permission to use the trade
      names, trademarks, service marks, or product names of the Licensor,
      except as required for reasonable and customary use in describing the
      origin of the Work and reproducing the content of the NOTICE file.

   7. Disclaimer of Warranty. Unless required by applicable law or
      agreed to in writing, Licensor provides the Work (and each
      Contributor provides its Contributions) on an "AS IS" BASIS,
      WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
      implied, including, without limitation, any warranties or conditions
      of TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A
      PARTICULAR PURPOSE. You are solely responsible for determining the
      appropriateness of using or redistributing the Work and assume any
      risks associated with Your exercise of permissions under this License.

   8. Limitation of Liability. In no event and under no legal theory,
      whether in tort (including negligence), contract, or otherwise,
      unless required by applicable law (such as deliberate and grossly
      negligent acts) or agreed to in writing, shall any Contributor be
      liable to You for damages, including any direct, indirect, special,
      incidental, or consequential damages of any character arising as a
      result of this License or out of the use or inability to use the
      Work (including but not limited to damages for loss of goodwill,
      work stoppage, computer failure or malfunction, or any and all
      other commercial damages or losses), even if such Contributor
      has been advised of the possibility of such damages.

   9. Accepting Warranty or Additional Liability. While redistributing
      the Work or Derivative Works thereof, You may choose to offer,
      and charge a fee for, acceptance of support, warranty, indemnity,
      or other liability obligations and/or rights consistent with this
      License. However, in accepting such obligations, You may act only
      on Your own behalf and on Your sole responsibility, not on behalf
      of any other Contributor, and only if You agree to indemnify,
      defend, and hold each Contributor harmless for any liability
      incurred by, or claims asserted against, such Contributor by reason
      of your accepting any such warranty or additional liability.

   END OF TERMS AND CONDITIONS

   APPENDIX: How to apply the Apache License to your work.

      To apply the Apache License to your work, attach the following
      boilerplate notice, with the fields enclosed by brackets "[]"
      replaced with your own identifying information. (Don't include
      the brackets!)  The text should be enclosed in the appropriate
      comment syntax for the file format. We also recommend that a
      file or class name and description of purpose be included on the
      same "printed page" as the copyright notice for easier
      identification within third-party archives.

   Copyright [yyyy] [name of copyright owner]

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
```


## 0.4.19 页面辅助图形

`bili_chevron_right`、`bili_drag_handle` 与 `bili_aux_audio/power/refresh/subtitle/volume` 是本项目为页面布局绘制的几何矢量，随项目源码提供。播放界面的轻量控制图形由 `PlayerChrome.Glyph` 绘制。它们不使用 Bilibili 的商标或图标文件；官方 Material Icons 资源的来源与许可仍按本文记录。
