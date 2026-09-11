#!/usr/bin/env node

/**
 * Clone the Unitree USD model dataset used by USD browser/fixture regression.
 * Sourced from the Unitree Hugging Face dataset (git-clone compatible).
 * Override with UNITREE_MODEL_URL if needed.
 */

import { cloneRepo, finishSingle } from './_clone-util.mjs';

const result = await cloneRepo({
  label: 'Unitree USD model dataset',
  url: process.env.UNITREE_MODEL_URL ?? 'https://huggingface.co/datasets/unitreerobotics/unitree_model',
  targetDir: 'test/unitree_model',
});

finishSingle(result);
