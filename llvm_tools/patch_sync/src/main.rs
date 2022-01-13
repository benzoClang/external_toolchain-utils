mod android_utils;
mod patch_parsing;
mod version_control;

use std::borrow::ToOwned;
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};
use structopt::StructOpt;

use patch_parsing::{filter_patches_by_platform, PatchCollection, PatchDictSchema};

fn main() -> Result<()> {
    match Opt::from_args() {
        Opt::Show {
            cros_checkout_path,
            android_checkout_path,
            sync,
            keep_unmerged,
        } => show_subcmd(ShowOpt {
            cros_checkout_path,
            android_checkout_path,
            sync,
            keep_unmerged,
        }),
        Opt::Transpose {
            cros_checkout_path,
            cros_reviewers,
            old_cros_ref,
            android_checkout_path,
            android_reviewers,
            old_android_ref,
            sync,
            verbose,
            dry_run,
            no_commit,
        } => transpose_subcmd(TransposeOpt {
            cros_checkout_path,
            cros_reviewers: cros_reviewers.split(',').map(ToOwned::to_owned).collect(),
            old_cros_ref,
            android_checkout_path,
            android_reviewers: android_reviewers
                .split(',')
                .map(ToOwned::to_owned)
                .collect(),
            old_android_ref,
            sync,
            verbose,
            dry_run,
            no_commit,
        }),
    }
}

struct ShowOpt {
    cros_checkout_path: PathBuf,
    android_checkout_path: PathBuf,
    keep_unmerged: bool,
    sync: bool,
}

fn show_subcmd(args: ShowOpt) -> Result<()> {
    let ShowOpt {
        cros_checkout_path,
        android_checkout_path,
        keep_unmerged,
        sync,
    } = args;
    let ctx = version_control::RepoSetupContext {
        cros_checkout: cros_checkout_path,
        android_checkout: android_checkout_path,
        sync_before: sync,
    };
    ctx.setup()?;
    let make_collection = |platform: &str, patches_fp: &Path| -> Result<PatchCollection> {
        let parsed_collection = PatchCollection::parse_from_file(patches_fp)
            .with_context(|| format!("could not parse {} PATCHES.json", platform))?;
        Ok(if keep_unmerged {
            parsed_collection
        } else {
            filter_patches_by_platform(&parsed_collection, platform).map_patches(|p| {
                PatchDictSchema {
                    platforms: BTreeSet::from([platform.to_string()]),
                    ..p.clone()
                }
            })
        })
    };
    let cur_cros_collection = make_collection("chromiumos", &ctx.cros_patches_path())?;
    let cur_android_collection = make_collection("android", &ctx.android_patches_path())?;
    let merged = cur_cros_collection.union(&cur_android_collection)?;
    println!("{}", merged.serialize_patches()?);
    Ok(())
}

struct TransposeOpt {
    cros_checkout_path: PathBuf,
    old_cros_ref: String,
    android_checkout_path: PathBuf,
    old_android_ref: String,
    sync: bool,
    verbose: bool,
    dry_run: bool,
    no_commit: bool,
    cros_reviewers: Vec<String>,
    android_reviewers: Vec<String>,
}

fn transpose_subcmd(args: TransposeOpt) -> Result<()> {
    let ctx = version_control::RepoSetupContext {
        cros_checkout: args.cros_checkout_path,
        android_checkout: args.android_checkout_path,
        sync_before: args.sync,
    };
    ctx.setup()?;
    let cros_patches_path = ctx.cros_patches_path();
    let android_patches_path = ctx.android_patches_path();

    // Get new Patches -------------------------------------------------------
    let (mut cur_cros_collection, new_cros_patches) = patch_parsing::new_patches(
        &cros_patches_path,
        &ctx.old_cros_patch_contents(&args.old_cros_ref)?,
        "chromiumos",
    )
    .context("finding new patches for chromiumos")?;
    let (mut cur_android_collection, new_android_patches) = patch_parsing::new_patches(
        &android_patches_path,
        &ctx.old_android_patch_contents(&args.old_android_ref)?,
        "android",
    )
    .context("finding new patches for android")?;

    // Have to ignore patches that are already at the destination, even if
    // the patches are new.
    let new_cros_patches = new_cros_patches.subtract(&cur_android_collection)?;
    let new_android_patches = new_android_patches.subtract(&cur_cros_collection)?;

    // Need to do an extra filtering step for Android, as AOSP doesn't
    // want patches outside of the start/end bounds.
    let android_llvm_version: u64 = {
        let android_llvm_version_str =
            android_utils::get_android_llvm_version(&ctx.android_checkout)?;
        android_llvm_version_str.parse::<u64>().with_context(|| {
            format!(
                "converting llvm version to u64: '{}'",
                android_llvm_version_str
            )
        })?
    };
    let new_android_patches =
        new_android_patches.filter_patches(|p| match (p.start_version, p.end_version) {
            (Some(start), Some(end)) => start <= android_llvm_version && android_llvm_version < end,
            (Some(start), None) => start <= android_llvm_version,
            (None, Some(end)) => android_llvm_version < end,
            (None, None) => true,
        });

    if args.verbose {
        display_patches("New patches from Chromium OS", &new_cros_patches);
        display_patches("New patches from Android", &new_android_patches);
    }

    if args.dry_run {
        println!("--dry-run specified; skipping modifications");
        return Ok(());
    }

    // Transpose Patches -----------------------------------------------------
    if !new_cros_patches.is_empty() {
        new_cros_patches.transpose_write(&mut cur_android_collection)?;
    }
    if !new_android_patches.is_empty() {
        new_android_patches.transpose_write(&mut cur_cros_collection)?;
    }

    if args.no_commit {
        println!("--no-commit specified; not committing or uploading");
        return Ok(());
    }
    // Commit and upload for review ------------------------------------------
    // Note we want to check if the android patches are empty for CrOS, and
    // vice versa. This is a little counterintuitive.
    if !new_android_patches.is_empty() {
        ctx.cros_repo_upload(&args.cros_reviewers)
            .context("uploading chromiumos changes")?;
    }
    if !new_cros_patches.is_empty() {
        ctx.android_repo_upload(&args.android_reviewers)
            .context("uploading android changes")?;
    }
    Ok(())
}

fn display_patches(prelude: &str, collection: &PatchCollection) {
    println!("{}", prelude);
    if collection.patches.is_empty() {
        println!("  [No Patches]");
        return;
    }
    println!("{}", collection);
}

#[derive(Debug, structopt::StructOpt)]
#[structopt(name = "patch_sync", about = "A pipeline for syncing the patch code")]
enum Opt {
    /// Show a combined view of the PATCHES.json file, without making any changes.
    #[allow(dead_code)]
    Show {
        #[structopt(parse(from_os_str))]
        cros_checkout_path: PathBuf,
        #[structopt(parse(from_os_str))]
        android_checkout_path: PathBuf,

        /// Keep a patch's platform field even if it's not merged at that platform.
        #[structopt(long)]
        keep_unmerged: bool,

        /// Run repo sync before transposing.
        #[structopt(short, long)]
        sync: bool,
    },
    /// Transpose patches from two PATCHES.json files
    /// to each other.
    Transpose {
        /// Path to the ChromiumOS source repo checkout.
        #[structopt(long = "cros-checkout", parse(from_os_str))]
        cros_checkout_path: PathBuf,

        /// Emails to send review requests to during Chromium OS upload.
        /// Comma separated.
        #[structopt(long = "cros-rev")]
        cros_reviewers: String,

        /// Git ref (e.g. hash) for the ChromiumOS overlay to use as the base.
        #[structopt(long = "overlay-base-ref")]
        old_cros_ref: String,

        /// Path to the Android Open Source Project source repo checkout.
        #[structopt(long = "aosp-checkout", parse(from_os_str))]
        android_checkout_path: PathBuf,

        /// Emails to send review requests to during Android upload.
        /// Comma separated.
        #[structopt(long = "aosp-rev")]
        android_reviewers: String,

        /// Git ref (e.g. hash) for the llvm_android repo to use as the base.
        #[structopt(long = "aosp-base-ref")]
        old_android_ref: String,

        /// Run repo sync before transposing.
        #[structopt(short, long)]
        sync: bool,

        /// Print information to stdout
        #[structopt(short, long)]
        verbose: bool,

        /// Do not change any files. Useful in combination with `--verbose`
        /// Implies `--no-commit`.
        #[structopt(long)]
        dry_run: bool,

        /// Do not commit or upload any changes made.
        #[structopt(long)]
        no_commit: bool,
    },
}
