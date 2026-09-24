function load_script(src, remote = true, transfer = []) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.onload = resolve;
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

async function doJb() {
  await load_script("css/misc.js");

  try {
    version.init();
    switch (version.console) {
      case 4:
        await load_script("css/ps4/constants.js");
        await load_script("css/ps4/userland.js");
        break;
      case 5:
        //TODO
        break;
      default:
        logger.info("Unsupported console " + version.console);
    }

    logger.info("===USERLAND===");

    let rw = undefined;
    if (arw.master === undefined) {
      rw = await init_rw();
    }

    init_arw(rw);
    init_rop();
    init_syscalls();

    logger.info("===END===");

    await load_script("css/loader.js");
    await load_script("css/workers.js");

    switch (version.console) {
      case 4:
        await load_script("css/ps4/kernel.js");
        break;
      case 5:
        //TODO
        break;
      default:
        logger.info("Unsupported console " + version.console);
    }

    if (fn.setuid.invoke(0) !== -1) {
      msgs.innerHTML = "GoldHEN is Already Loaded ...";
      return;
    }

    // [H0sS F2] PS4 WebKit storage can throw after kernel R/W -- guarded
    // read with a whitelist (the only chains this page ships)
    var exploitChain = "lapse";
    try {
      var savedChain = localStorage.getItem("exploitChain");
      if (savedChain === "poops" || savedChain === "lapse") {
        exploitChain = savedChain;
      }
    } catch (e) { }
    await load_script("css/" + exploitChain + ".js");
    logger.info("===" + exploitChain.toUpperCase() + "===");

    try {
      if (exploitChain == "lapse") {
        init();
        await setup();
        await double_free_reqs2();
        leak_kaddrs();
        double_free_reqs1();
        make_karw();
        inc_karw_pipe_refcnt();

        logger.info("Corrupted context cleanup started...");
        remove_pktinfo_from_so(pktopts_twins[0]);
        remove_rthdr_from_so(pktopts_twins[1]);
        remove_rthdr_from_so(rthdr_twins[0]);
        logger.info("Corrupted context cleanup completed !!");
      } else {
        init();
        await setup();
        await ucred_triple_free();
        leak_kqueue();
        await make_karw();
        inc_karw_pipe_refcnt();

        logger.info("Corrupted context cleanup started...");
        for (let i = 0; i < triplets.length; i++) {
          remove_rthdr_from_so(triplets[i]);
        }
        remove_uaf_file();
        logger.info("Corrupted context cleanup completed !!");
      }
    } finally {
      cleanup();
    }

    find_all_proc();

    // H0sS: ?bin=<path> override (PKG-BackUP tool launcher). When set, we
    // always re-run jailbreak + kpatch + payload so the tool payload is
    // delivered even if the console is already rooted from an earlier run.
    // jailbreak() re-writes the same ucred/fd values, so it is idempotent.
    const ovrBin = new URLSearchParams(location.search).get("bin");
    if (fn.setuid.invoke(0) === -1 || ovrBin) {
      jailbreak();

      const kpatches_rsp = await fetch("css/ps4/patches/" + constants.KPATCH);
      const kpatches_buf = await kpatches_rsp.arrayBuffer();
      const kpatches_u8 = new Uint8Array(kpatches_buf);
      kernel_patches(kpatches_u8);

      const bin_rsp = await fetch(ovrBin || "goldhen_2.4b18.10.bin");
      const bin_buf = await bin_rsp.arrayBuffer();
      const bin_u8 = new Uint8Array(bin_buf);
      load_bin(bin_u8);
    }

    msgs.innerHTML = ovrBin
      ? "PKG-BackUP v1.3 Loaded — النسخ شغال، لا تغلق الصفحة ولا تفصل الفلاشة ..."
      : "GoldHEN v2.4b18.10 Loaded ...";
    logger.info("===END===");
  } catch (e) {
    // [H0sS F6] unified failure guidance (Arabic-first, same wording as the
    // 700/900 lapse chains)
    msgs.innerHTML = 'فشل تحميل الجيلبريك — حدّث الصفحة (F5) وأعد المحاولة، ولو استمر الفشل اعمل ريستارت للجهاز';
    msgs.style.color = "yellow";
  }
}