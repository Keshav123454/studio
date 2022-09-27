import Vue from 'vue';
import { mergeMapItem } from 'shared/vuex/utils';
import { applyMods } from 'shared/data/applyRemoteChanges';

function updateFileMaps(state, file) {
  if (file.assessment_item) {
    state.assessmentItemFilesMap = {
      ...state.assessmentItemFilesMap,
      [file.assessment_item]: {
        ...state.assessmentItemFilesMap[file.assessment_item],
        [file.id]: file,
      },
    };
  } else if (file.contentnode) {
    state.contentNodeFilesMap = {
      ...state.contentNodeFilesMap,
      [file.contentnode]: {
        ...state.contentNodeFilesMap[file.contentnode],
        [file.id]: file,
      },
    };
  }
}

export function ADD_FILE(state, file) {
  if (!file.id) {
    return;
  }
  state.fileUploadsMap = mergeMapItem(state.fileUploadsMap || {}, file);
  // Get the merged item in case there is incomplete information in the file payload
  file = state.fileUploadsMap[file.id];
  updateFileMaps(state, file);
}

export function ADD_FILES(state, files = []) {
  files.forEach(file => {
    ADD_FILE(state, file);
  });
}

export function UPDATE_FILE_FROM_INDEXEDDB(state, { id, ...mods }) {
  if (id && state.fileUploadsMap[id]) {
    state.fileUploadsMap = {
      ...state.fileUploadsMap,
      [id]: applyMods(state.fileUploadsMap[id], mods),
    };
    updateFileMaps(state, state.fileUploadsMap[id]);
  }
}

export function REMOVE_FILE(state, file) {
  if (!file.id) {
    return;
  }
  Vue.delete(state.fileUploadsMap, file.id);
  if (file.assessment_item) {
    Vue.delete(state.assessmentItemFilesMap[file.assessment_item], file.id);
  } else if (file.contentnode) {
    Vue.delete(state.contentNodeFilesMap[file.contentnode], file.id);
  }
}
