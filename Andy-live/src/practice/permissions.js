function isAllowedRequest(permission, details) {
    return permission === 'media' && Array.isArray(details?.mediaTypes) &&
        details.mediaTypes.includes('audio') && !details.mediaTypes.includes('video');
}

function isAllowedCheck(permission, details) {
    return permission === 'media' && details?.mediaType === 'audio';
}

module.exports = { isAllowedRequest, isAllowedCheck };
