function updateTargetSheets() {
  // CONFIGURATION
  const sourceSpreadsheetId = '1VF7g11oCrXS4q-YFscOEZ_0lYmexosdc_dn7AgOSv_E'; 
  const tabName = 'Stocks'; // Using 'Stocks' for both source and target
  
  // List of Target Spreadsheet IDs
  const targetIds = [
    "1cEku5it1m_zObE3FJ6R8nnbbfqNpM2CSvCdbTo_1zbw",
    "1avA987qiFJlDubV-fTwSDGH60YUg-0aJ1hdm63o5FSo",
    "15kDExlBcHSpQVXHQIa_rSRc1o42NQdaZHZjs5aTRMkU",
    "10ye5zgrEQxBQQElBzuTLZJtwm1IXyeKVh-A742yuv94",
    "1wWLcjlHXiht426ECNZkGziDyY_WiKV_ICX6maA7Wuk4",
    "1l6HzSYIQjJPixNQ_FF0rA5zf5Yq_y6n7r7mjZuQXyFo",
    "1UHm-S9D-sfa9QijZqEF8uX4jYXP4HlT7jIAMA6J4Jts",
    "1500DMTR1ypTvpKzSBUyzLh-KlI_C8Fk0GvRYVhQkshA",
    "1OMltNQnkjWJsEKTPSbRPiogFbqhTzZsH-mPuN3MYzEI",
    "1g-PbfDsj_J_aJYxN0ddiFn9IHlrTC-LpzyxsPSn6hGo",
    "1kPRiSE_7m1TZPjWTOPBp-RBPrulJsjAGQZjvCR5GFwQ",
    "1DrPAmeQBRNpdS0znWP8HxloalDIbu0InXzUZr_EUVEw",
    "1IH9XUOThqQGaB0rQ4TJycm0zFVbyWNu42QK3MrJBzO4",
    "1fo5xPahUqIOliTvSJKn_x8LRAXTl2q6vMXnWK01-Z2E",
    "1dkczRUmKBFz_iuw-lld-xrSyY304WzwLivKpHSe0KCI",
    "1qE1hzNI4JpxWWAEh6BwbMxEoNz0WahjN_7JCk2JJo8Q",
    "1mQlBo_30hU2Gj5now83UGAAJTKDpn6w_KSog4sLuWFo",
    "1QTYYfn0tTh-fK8mjcfmnJwMjPlyZ4i4ZTnBgFYSNqho",
    "1ffcnqOLP7wdVVCd8pVVjUTqZl9c23ML4dPYC9v52AZ4",
    "132jVkk2P24zrx9fuAG0AcXuTBfIKI5RWC8WpNAhpnJo",
    "1xRwP7cQl_IwqBc_xVvIe49_9E72F8gV8__djGDAPDK0",
    "1MmSnnVXzgWnPztwm5DVGEOX3EwFOXlHeSfvT_1Yu4Tk",
    "1-KkWCL__TVhzXliqBXvrTbWrn6vwNfQIoyVvmqymdns",
    "1O0g3qQVS-uhXNwulwGRvUBxm3yaTjdmolJAGb-YnKKU",
    "1z132H_kmwWqHrWEbNViEWMOWuU7rWL5Xzv7ffxo9crU",
    "1qpl8uby0WFlSpMvoGmDkofiqOZDPy70R42hGi4A8JAs",
    "1E5hEXnYQQJm1BZv0GUZTfvAF47HXauZS3TMwFk6xS-k",
    "15LeWfOitdmSLP9ak_Ss5iFg579fhg49v7pL--a_Zu3E"
  ];

  // Get data from source
  const sourceSS = SpreadsheetApp.openById(sourceSpreadsheetId);
  const sourceSheet = sourceSS.getSheetByName(tabName);
  const sourceData = sourceSheet.getRange(1, 1, sourceSheet.getLastRow(), 3).getValues();

  // Update target sheets
  targetIds.forEach(id => {
    try {
      const targetSS = SpreadsheetApp.openById(id);
      const targetSheet = targetSS.getSheetByName(tabName);
      
      if (targetSheet) {
        targetSheet.clearContents();
        targetSheet.getRange(1, 1, sourceData.length, 3).setValues(sourceData);
        Logger.log('Updated: ' + id);
      }
    } catch (e) {
      Logger.log('Error updating ' + id + ': ' + e.toString());
    }
  });
}
