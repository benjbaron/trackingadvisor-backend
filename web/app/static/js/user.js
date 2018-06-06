mapboxgl.accessToken = 'pk.eyJ1IjoiYmVuamJhcm9uIiwiYSI6InItaHotTkkifQ.Im25SdEu7d8FNUSXKq8orA';
var pointsLayer = false;

var map = new mapboxgl.Map({
    container: 'map',
    style: 'mapbox://styles/mapbox/dark-v9',
    center: [-96, 37.8],
    zoom: 3
});

function init() {
    map.addControl(new mapboxgl.NavigationControl());
}

map.on('load', init);


$(function() {
    setTimeout(function() {
        var params = {
            login: login
        }
        console.log("getting user summary")
        $.getJSON('/usersummary', params, function (data) {
            console.log(data)
        });
    }, 2000);
});